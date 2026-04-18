package com.brokenlunch.gr.ui.recommend

import android.Manifest
import android.annotation.SuppressLint
import android.app.Application
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.brokenlunch.gr.data.ApiResult
import com.brokenlunch.gr.data.model.Recommendation
import com.brokenlunch.gr.data.repository.GeminiRepository
import com.brokenlunch.gr.ui.map.GR_CENTER
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.maps.model.LatLng
import com.google.android.gms.tasks.CancellationTokenSource
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

enum class RecommendStage { IDLE, LOADING, RESULT, ERROR }

data class RecommendUiState(
    val stage: RecommendStage = RecommendStage.IDLE,
    val query: String = "",
    val lastSubmittedQuery: String = "",
    val recommendations: List<Recommendation> = emptyList(),
    val error: String? = null,
    val center: LatLng = GR_CENTER,
)

@HiltViewModel
class RecommendViewModel @Inject constructor(
    app: Application,
    private val geminiRepo: GeminiRepository,
) : AndroidViewModel(app) {

    private val _state = MutableStateFlow(RecommendUiState())
    val state: StateFlow<RecommendUiState> = _state.asStateFlow()

    private val fused = LocationServices.getFusedLocationProviderClient(app)

    fun setQuery(text: String) {
        _state.value = _state.value.copy(query = text)
    }

    fun submit() {
        val q = _state.value.query.trim()
        if (q.isEmpty()) return
        _state.value = _state.value.copy(
            stage = RecommendStage.LOADING,
            lastSubmittedQuery = q,
            error = null,
        )
        resolveLocationThenSearch(q)
    }

    fun reset() {
        _state.value = _state.value.copy(
            stage = RecommendStage.IDLE,
            recommendations = emptyList(),
            error = null,
        )
    }

    private fun resolveLocationThenSearch(q: String) {
        val ctx = getApplication<Application>()
        val granted = ContextCompat.checkSelfPermission(
            ctx, Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        if (!granted) {
            search(q, _state.value.center)
            return
        }
        fetchLocation { c ->
            _state.value = _state.value.copy(center = c)
            search(q, c)
        }
    }

    @SuppressLint("MissingPermission")
    private fun fetchLocation(onResolved: (LatLng) -> Unit) {
        val cts = CancellationTokenSource()
        fused.getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY, cts.token)
            .addOnSuccessListener { loc ->
                onResolved(if (loc != null) LatLng(loc.latitude, loc.longitude) else _state.value.center)
            }
            .addOnFailureListener { onResolved(_state.value.center) }
    }

    private fun search(q: String, c: LatLng) {
        viewModelScope.launch {
            when (val r = geminiRepo.recommend(c.latitude, c.longitude, q, maxResults = 3)) {
                is ApiResult.Success -> {
                    val recs = r.data.recommendations
                    _state.value = if (recs.isEmpty()) {
                        _state.value.copy(
                            stage = RecommendStage.ERROR,
                            error = "Sorry, couldn't find a match. Try different keywords.",
                        )
                    } else {
                        _state.value.copy(stage = RecommendStage.RESULT, recommendations = recs)
                    }
                }
                is ApiResult.HttpError -> _state.value = _state.value.copy(
                    stage = RecommendStage.ERROR,
                    error = "Recommendation failed (error ${r.code}).",
                )
                is ApiResult.NetworkError -> _state.value = _state.value.copy(
                    stage = RecommendStage.ERROR,
                    error = "Can't reach server — check your connection.",
                )
            }
        }
    }
}
