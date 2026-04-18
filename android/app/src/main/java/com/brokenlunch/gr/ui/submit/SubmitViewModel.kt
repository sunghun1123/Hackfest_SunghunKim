package com.brokenlunch.gr.ui.submit

import android.Manifest
import android.annotation.SuppressLint
import android.app.Application
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.viewModelScope
import com.brokenlunch.gr.data.ApiResult
import com.brokenlunch.gr.data.model.GeminiParsedInfo
import com.brokenlunch.gr.data.model.ParsedMenuItem
import com.brokenlunch.gr.data.model.RestaurantNearby
import com.brokenlunch.gr.data.model.SubmissionRequest
import com.brokenlunch.gr.data.model.SubmissionResponse
import com.brokenlunch.gr.data.repository.GeminiRepository
import com.brokenlunch.gr.data.repository.RestaurantRepository
import com.brokenlunch.gr.data.repository.SubmissionRepository
import com.brokenlunch.gr.ui.map.GR_CENTER
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.maps.model.LatLng
import com.google.android.gms.tasks.CancellationTokenSource
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.UUID
import javax.inject.Inject

const val SUBMIT_ARG_RESTAURANT_ID = "restaurantId"

enum class SubmitStage {
    SELECTING_RESTAURANT,
    CAMERA_OPEN,
    PARSING,
    EDITING,
    SUBMITTING,
    DONE,
}

data class EditableItem(
    val clientId: String = UUID.randomUUID().toString(),
    val name: String,
    val priceText: String,
    val confidence: Double? = null,  // null = manual add
    val fromGemini: Boolean = false,
    val rawLine: String? = null,
) {
    fun priceCents(): Int? {
        val v = priceText.trim().toDoubleOrNull() ?: return null
        if (v <= 0) return null
        return (v * 100).toInt()
    }

    fun isValid(): Boolean = name.isNotBlank() && priceCents() != null
    fun needsReview(): Boolean = confidence != null && confidence < 0.6
}

data class SubmitResult(
    val totalPoints: Int = 0,
    val firstSubmissionBonuses: Int = 0,
    val successCount: Int = 0,
    val failureCount: Int = 0,
    val levelUp: Boolean = false,
    val finalLevel: Int = 0,
)

data class SubmitUiState(
    val stage: SubmitStage = SubmitStage.SELECTING_RESTAURANT,
    val restaurantId: String? = null,
    val restaurantName: String? = null,
    val nearbyRestaurants: List<RestaurantNearby> = emptyList(),
    val searchQuery: String = "",
    val items: List<EditableItem> = emptyList(),
    val parseWarnings: List<String> = emptyList(),
    val error: String? = null,
    val result: SubmitResult = SubmitResult(),
    val center: LatLng = GR_CENTER,
)

@HiltViewModel
class SubmitViewModel @Inject constructor(
    app: Application,
    savedStateHandle: SavedStateHandle,
    private val restaurantRepo: RestaurantRepository,
    private val geminiRepo: GeminiRepository,
    private val submissionRepo: SubmissionRepository,
) : AndroidViewModel(app) {

    private val _state = MutableStateFlow(SubmitUiState())
    val state: StateFlow<SubmitUiState> = _state.asStateFlow()

    private val fused = LocationServices.getFusedLocationProviderClient(app)

    init {
        val preFilledId = savedStateHandle.get<String>(SUBMIT_ARG_RESTAURANT_ID)
        if (!preFilledId.isNullOrBlank() && preFilledId != "none") {
            _state.value = _state.value.copy(
                restaurantId = preFilledId,
                stage = SubmitStage.CAMERA_OPEN,
            )
        } else {
            loadNearbyForPicker()
        }
    }

    private fun loadNearbyForPicker() {
        val ctx = getApplication<Application>()
        val granted = ContextCompat.checkSelfPermission(
            ctx, Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        if (granted) fetchLocationThenLoad() else loadFromCenter(_state.value.center)
    }

    @SuppressLint("MissingPermission")
    private fun fetchLocationThenLoad() {
        val cts = CancellationTokenSource()
        fused.getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY, cts.token)
            .addOnSuccessListener { loc ->
                val c = if (loc != null) LatLng(loc.latitude, loc.longitude) else _state.value.center
                _state.value = _state.value.copy(center = c)
                loadFromCenter(c)
            }
            .addOnFailureListener { loadFromCenter(_state.value.center) }
    }

    private fun loadFromCenter(c: LatLng) {
        viewModelScope.launch {
            val result = restaurantRepo.nearby(
                lat = c.latitude,
                lng = c.longitude,
                radiusM = 3000,
                includeEmpty = true,
                limit = 100,
            )
            if (result is ApiResult.Success) {
                _state.value = _state.value.copy(nearbyRestaurants = result.data.restaurants)
            }
        }
    }

    fun setSearchQuery(q: String) {
        _state.value = _state.value.copy(searchQuery = q)
    }

    fun selectRestaurant(r: RestaurantNearby) {
        _state.value = _state.value.copy(
            restaurantId = r.id,
            restaurantName = r.name,
            stage = SubmitStage.CAMERA_OPEN,
        )
    }

    fun openCamera() {
        _state.value = _state.value.copy(stage = SubmitStage.CAMERA_OPEN, error = null)
    }

    fun cancelCamera() {
        val s = _state.value
        _state.value = s.copy(
            stage = if (s.items.isNotEmpty()) SubmitStage.EDITING
            else if (s.restaurantId == null) SubmitStage.SELECTING_RESTAURANT
            else SubmitStage.CAMERA_OPEN,
        )
    }

    fun onPhotoCaptured(rawJpegBytes: ByteArray) {
        _state.value = _state.value.copy(stage = SubmitStage.PARSING, error = null)
        viewModelScope.launch {
            val downsampled = withContext(Dispatchers.Default) { downsampleJpeg(rawJpegBytes) }
            android.util.Log.d(
                "SubmitViewModel",
                "Sending ${downsampled.bytes.size} bytes (${downsampled.width}x${downsampled.height}) image/jpeg to /parse-menu-image",
            )
            when (val result = geminiRepo.parseMenuImage(downsampled.bytes)) {
                is ApiResult.Success -> {
                    val parsed = result.data
                    val editable = parsed.items.map { it.toEditable() }
                    if (editable.isEmpty()) {
                        _state.value = _state.value.copy(
                            stage = SubmitStage.EDITING,
                            items = listOf(emptyManualItem()),
                            parseWarnings = parsed.warnings + "Couldn't read the menu. Add items manually.",
                        )
                    } else {
                        _state.value = _state.value.copy(
                            stage = SubmitStage.EDITING,
                            items = editable,
                            parseWarnings = parsed.warnings,
                        )
                    }
                }
                is ApiResult.HttpError -> _state.value = _state.value.copy(
                    stage = SubmitStage.CAMERA_OPEN,
                    error = "Parsing failed (error ${result.code})",
                )
                is ApiResult.NetworkError -> _state.value = _state.value.copy(
                    stage = SubmitStage.CAMERA_OPEN,
                    error = "Can't reach server — check connection",
                )
            }
        }
    }

    fun updateItemName(index: Int, name: String) = updateItem(index) { it.copy(name = name) }
    fun updateItemPrice(index: Int, priceText: String) = updateItem(index) { it.copy(priceText = priceText) }
    fun deleteItem(index: Int) {
        val current = _state.value.items
        if (index !in current.indices) return
        _state.value = _state.value.copy(items = current.toMutableList().apply { removeAt(index) })
    }

    fun addManualItem() {
        _state.value = _state.value.copy(items = _state.value.items + emptyManualItem())
    }

    fun retakePhoto() {
        _state.value = _state.value.copy(
            stage = SubmitStage.CAMERA_OPEN,
            items = emptyList(),
            parseWarnings = emptyList(),
            error = null,
        )
    }

    fun submitAll() {
        val s = _state.value
        val restaurantId = s.restaurantId ?: run {
            _state.value = s.copy(error = "No restaurant selected")
            return
        }
        val validItems = s.items.filter { it.isValid() }
        if (validItems.isEmpty()) {
            _state.value = s.copy(error = "Add at least one valid item (name + price)")
            return
        }
        _state.value = s.copy(stage = SubmitStage.SUBMITTING, error = null)

        viewModelScope.launch {
            val deferred: List<Deferred<ApiResult<SubmissionResponse>>> = validItems.map { item ->
                async {
                    val body = SubmissionRequest(
                        restaurantId = restaurantId,
                        menuName = item.name.trim(),
                        priceCents = item.priceCents()!!,
                        photoUrl = null,
                        geminiParsed = item.confidence?.let { GeminiParsedInfo(confidence = it) },
                        source = if (item.fromGemini) "user_with_gemini" else "user_manual",
                    )
                    submissionRepo.submit(body)
                }
            }
            val responses = deferred.awaitAll()
            var total = 0
            var first = 0
            var ok = 0
            var fail = 0
            var levelUp = false
            var finalLevel = 0
            responses.forEach { resp ->
                when (resp) {
                    is ApiResult.Success -> {
                        ok++
                        total += resp.data.pointsAwarded
                        if (resp.data.isFirstSubmission) first++
                        if (resp.data.levelUp) levelUp = true
                        finalLevel = resp.data.userLevel
                    }
                    is ApiResult.HttpError,
                    is ApiResult.NetworkError -> fail++
                }
            }
            _state.value = _state.value.copy(
                stage = SubmitStage.DONE,
                result = SubmitResult(
                    totalPoints = total,
                    firstSubmissionBonuses = first,
                    successCount = ok,
                    failureCount = fail,
                    levelUp = levelUp,
                    finalLevel = finalLevel,
                ),
            )
        }
    }

    fun clearError() {
        _state.value = _state.value.copy(error = null)
    }

    private inline fun updateItem(index: Int, transform: (EditableItem) -> EditableItem) {
        val current = _state.value.items
        if (index !in current.indices) return
        _state.value = _state.value.copy(
            items = current.toMutableList().apply { this[index] = transform(this[index]) },
        )
    }
}

private fun ParsedMenuItem.toEditable(): EditableItem = EditableItem(
    name = name,
    priceText = "%.2f".format(priceCents / 100.0),
    confidence = confidence,
    fromGemini = true,
)

private fun emptyManualItem(): EditableItem = EditableItem(
    name = "",
    priceText = "",
    confidence = null,
    fromGemini = false,
)
