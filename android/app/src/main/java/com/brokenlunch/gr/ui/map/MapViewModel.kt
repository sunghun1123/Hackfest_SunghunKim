package com.brokenlunch.gr.ui.map

import android.Manifest
import android.annotation.SuppressLint
import android.app.Application
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.brokenlunch.gr.data.ApiResult
import com.brokenlunch.gr.data.model.MenuStatus
import com.brokenlunch.gr.data.model.RestaurantNearby
import com.brokenlunch.gr.data.model.Tier
import com.brokenlunch.gr.data.repository.RestaurantRepository
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import com.google.maps.android.compose.CameraPositionState
import com.google.android.gms.maps.model.LatLng
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.launch
import javax.inject.Inject

val GR_CENTER = LatLng(42.9634, -85.6681)
const val DEFAULT_ZOOM = 13f
const val FALLBACK_ZOOM = 12f

data class MapUiState(
    val center: LatLng = GR_CENTER,
    val userLocation: LatLng? = null,
    val selectedTiers: Set<Tier> = emptySet(),
    val showEmpty: Boolean = true,
    val restaurants: List<RestaurantNearby> = emptyList(),
    val loading: Boolean = false,
    val error: String? = null,
    val locationPermissionDenied: Boolean = false,
)

@OptIn(FlowPreview::class)
@HiltViewModel
class MapViewModel @Inject constructor(
    app: Application,
    private val repo: RestaurantRepository,
) : AndroidViewModel(app) {

    private val _state = MutableStateFlow(MapUiState())
    val state: StateFlow<MapUiState> = _state.asStateFlow()

    private val fused = LocationServices.getFusedLocationProviderClient(app)

    private val filterTrigger = MutableStateFlow(FilterKey())

    init {
        filterTrigger
            .drop(1)  // skip initial emission; explicit loadNearby() handles first fetch
            .distinctUntilChanged()
            .debounce(300)
            .onEach { loadNearby() }
            .launchIn(viewModelScope)
    }

    private data class FilterKey(
        val tiers: Set<Tier> = emptySet(),
        val showEmpty: Boolean = true,
    )

    fun toggleTier(tier: Tier) {
        val current = _state.value.selectedTiers
        val next = if (tier in current) current - tier else current + tier
        _state.value = _state.value.copy(selectedTiers = next)
        filterTrigger.value = FilterKey(next, _state.value.showEmpty)
    }

    fun toggleShowEmpty(show: Boolean) {
        _state.value = _state.value.copy(showEmpty = show)
        filterTrigger.value = FilterKey(_state.value.selectedTiers, show)
    }

    fun onLocationPermissionGranted() {
        _state.value = _state.value.copy(locationPermissionDenied = false)
        fetchLastLocation()
    }

    fun onLocationPermissionDenied() {
        _state.value = _state.value.copy(
            locationPermissionDenied = true,
            center = GR_CENTER,
            userLocation = null,
        )
        loadNearby()
    }

    @SuppressLint("MissingPermission")
    private fun fetchLastLocation() {
        val ctx = getApplication<Application>()
        val granted = ContextCompat.checkSelfPermission(
            ctx,
            Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        if (!granted) {
            onLocationPermissionDenied()
            return
        }
        val cts = CancellationTokenSource()
        fused.getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY, cts.token)
            .addOnSuccessListener { loc ->
                if (loc != null) {
                    val ll = LatLng(loc.latitude, loc.longitude)
                    _state.value = _state.value.copy(userLocation = ll, center = ll)
                } else {
                    _state.value = _state.value.copy(center = GR_CENTER)
                }
                loadNearby()
            }
            .addOnFailureListener {
                _state.value = _state.value.copy(center = GR_CENTER)
                loadNearby()
            }
    }

    fun recenterToUser(cameraState: CameraPositionState) {
        val user = _state.value.userLocation ?: return
        viewModelScope.launch {
            cameraState.animate(
                com.google.android.gms.maps.CameraUpdateFactory.newLatLngZoom(user, DEFAULT_ZOOM),
            )
        }
    }

    fun loadNearby() {
        val center = _state.value.center
        val showEmpty = _state.value.showEmpty
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            val result = repo.nearby(
                lat = center.latitude,
                lng = center.longitude,
                radiusM = 2000,
                tier = null,  // server returns all; tier multi-select filtered client-side
                includeEmpty = showEmpty,
                limit = 200,
            )
            when (result) {
                is ApiResult.Success -> _state.value = _state.value.copy(
                    restaurants = result.data.restaurants,
                    loading = false,
                    error = null,
                )
                is ApiResult.HttpError -> _state.value = _state.value.copy(
                    loading = false,
                    error = "Server error ${result.code}",
                )
                is ApiResult.NetworkError -> _state.value = _state.value.copy(
                    loading = false,
                    error = "Can't reach server",
                )
            }
        }
    }

    fun visibleRestaurants(): List<RestaurantNearby> {
        val s = _state.value
        val tiers = s.selectedTiers
        return s.restaurants.filter { r ->
            if (tiers.isEmpty()) return@filter true
            when (r.menuStatus) {
                MenuStatus.EMPTY -> true  // tier doesn't apply; show if empty toggle allows it
                MenuStatus.POPULATED_VERIFIED,
                MenuStatus.POPULATED_AI -> r.cheapestMenu?.tier in tiers
            }
        }
    }
}
