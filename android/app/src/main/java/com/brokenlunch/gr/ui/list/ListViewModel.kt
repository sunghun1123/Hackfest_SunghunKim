package com.brokenlunch.gr.ui.list

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

enum class SortMode { DISTANCE, PRICE }

data class ListSection(
    val id: String,
    val title: String,
    val subtitle: String,
    val restaurants: List<RestaurantNearby>,
    val tier: Tier?,  // null for Help us section
)

data class ListUiState(
    val center: LatLng = GR_CENTER,
    val sortMode: SortMode = SortMode.DISTANCE,
    val showEmpty: Boolean = true,
    val sections: List<ListSection> = emptyList(),
    val loading: Boolean = false,
    val error: String? = null,
)

@HiltViewModel
class ListViewModel @Inject constructor(
    app: Application,
    private val repo: RestaurantRepository,
) : AndroidViewModel(app) {

    private val _state = MutableStateFlow(ListUiState())
    val state: StateFlow<ListUiState> = _state.asStateFlow()

    private val fused = LocationServices.getFusedLocationProviderClient(app)

    fun initIfNeeded() {
        if (_state.value.sections.isNotEmpty() || _state.value.loading) return
        val ctx = getApplication<Application>()
        val granted = ContextCompat.checkSelfPermission(
            ctx, Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        if (granted) fetchLocationThenLoad() else load()
    }

    fun setSort(mode: SortMode) {
        if (_state.value.sortMode == mode) return
        _state.value = _state.value.copy(sortMode = mode)
        rebuildSections(_state.value.sections.flatMap { it.restaurants })
    }

    fun setShowEmpty(show: Boolean) {
        if (_state.value.showEmpty == show) return
        _state.value = _state.value.copy(showEmpty = show)
        load()
    }

    @SuppressLint("MissingPermission")
    private fun fetchLocationThenLoad() {
        val cts = CancellationTokenSource()
        fused.getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY, cts.token)
            .addOnSuccessListener { loc ->
                if (loc != null) {
                    _state.value = _state.value.copy(center = LatLng(loc.latitude, loc.longitude))
                }
                load()
            }
            .addOnFailureListener { load() }
    }

    fun load() {
        val center = _state.value.center
        val showEmpty = _state.value.showEmpty
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            val result = repo.nearby(
                lat = center.latitude,
                lng = center.longitude,
                radiusM = 2000,
                tier = null,
                includeEmpty = showEmpty,
                limit = 200,
            )
            when (result) {
                is ApiResult.Success -> rebuildSections(result.data.restaurants)
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

    private fun rebuildSections(all: List<RestaurantNearby>) {
        val sort = _state.value.sortMode
        val byTier: Map<Tier, List<RestaurantNearby>> = all
            .filter { it.menuStatus != MenuStatus.EMPTY && it.cheapestMenu != null }
            .groupBy { it.cheapestMenu!!.tier }
            .mapValues { (_, list) -> sortRestaurants(list, sort) }

        val emptyList = all.filter { it.menuStatus == MenuStatus.EMPTY }.sortedBy { it.distanceM }

        val sections = buildList {
            byTier[Tier.SURVIVE]?.takeIf { it.isNotEmpty() }?.let {
                add(ListSection("survive", "Survive", "$0 - $5 · eat to live", it, Tier.SURVIVE))
            }
            byTier[Tier.COST_EFFECTIVE]?.takeIf { it.isNotEmpty() }?.let {
                add(ListSection("cost_effective", "Cost-effective", "$5 - $10 · solid meal", it, Tier.COST_EFFECTIVE))
            }
            byTier[Tier.LUXURY]?.takeIf { it.isNotEmpty() }?.let {
                add(ListSection("luxury", "Luxury", "$10 - $15 · treat yourself", it, Tier.LUXURY))
            }
            if (emptyList.isNotEmpty()) {
                add(ListSection("help", "Help us!", "menus missing nearby · be the first", emptyList, null))
            }
        }
        _state.value = _state.value.copy(sections = sections, loading = false)
    }

    private fun sortRestaurants(list: List<RestaurantNearby>, sort: SortMode): List<RestaurantNearby> =
        when (sort) {
            SortMode.DISTANCE -> list.sortedBy { it.distanceM }
            SortMode.PRICE -> list.sortedBy { it.cheapestMenu?.priceCents ?: Int.MAX_VALUE }
        }
}
