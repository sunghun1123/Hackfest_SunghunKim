package com.brokenlunch.gr.ui.detail

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.brokenlunch.gr.data.ApiResult
import com.brokenlunch.gr.data.model.MeResponse
import com.brokenlunch.gr.data.model.MenuItem
import com.brokenlunch.gr.data.model.ReportReason
import com.brokenlunch.gr.data.model.RestaurantDetail
import com.brokenlunch.gr.data.model.Tier
import com.brokenlunch.gr.data.model.VerificationStatus
import com.brokenlunch.gr.data.repository.MeRepository
import com.brokenlunch.gr.data.repository.RestaurantRepository
import com.brokenlunch.gr.data.repository.SubmissionRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

const val DETAIL_ARG_ID = "restaurantId"

data class DetailUiState(
    val restaurant: RestaurantDetail? = null,
    val me: MeResponse? = null,
    val loading: Boolean = true,
    val error: String? = null,
    val confirmingIds: Set<String> = emptySet(),
)

sealed class DetailEvent {
    data class Toast(val message: String) : DetailEvent()
}

@HiltViewModel
class DetailViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val restaurantRepo: RestaurantRepository,
    private val submissionRepo: SubmissionRepository,
    private val meRepo: MeRepository,
) : ViewModel() {

    val restaurantId: String = checkNotNull(savedStateHandle[DETAIL_ARG_ID]) {
        "Detail screen requires '$DETAIL_ARG_ID' nav argument"
    }

    private val _state = MutableStateFlow(DetailUiState())
    val state: StateFlow<DetailUiState> = _state.asStateFlow()

    private val _events = MutableSharedFlow<DetailEvent>(extraBufferCapacity = 4)
    val events: SharedFlow<DetailEvent> = _events.asSharedFlow()

    init {
        loadDetail()
        loadMe()
    }

    fun loadDetail() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            when (val result = restaurantRepo.detail(restaurantId)) {
                is ApiResult.Success -> _state.value = _state.value.copy(
                    restaurant = result.data,
                    loading = false,
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

    private fun loadMe() {
        viewModelScope.launch {
            when (val result = meRepo.me()) {
                is ApiResult.Success -> _state.value = _state.value.copy(me = result.data)
                else -> {}  // non-fatal; rate button just stays hidden
            }
        }
    }

    fun confirmPrice(menuItemId: String) {
        markConfirming(menuItemId, true)
        viewModelScope.launch {
            when (val result = submissionRepo.confirm(menuItemId, isAgreement = true)) {
                is ApiResult.Success -> {
                    applyMenuItemUpdate(result.data.menuItemUpdated)
                    emit(DetailEvent.Toast("+${result.data.pointsAwarded} points"))
                }
                is ApiResult.HttpError -> emit(
                    DetailEvent.Toast(
                        if (result.code == 409) "You already confirmed this"
                        else "Couldn't confirm (error ${result.code})",
                    ),
                )
                is ApiResult.NetworkError -> emit(DetailEvent.Toast("Network error — try again"))
            }
            markConfirming(menuItemId, false)
        }
    }

    fun reportDifferentPrice(menuItemId: String, reportedPriceCents: Int) {
        markConfirming(menuItemId, true)
        viewModelScope.launch {
            when (val result = submissionRepo.confirm(
                menuItemId = menuItemId,
                isAgreement = false,
                reportedPrice = reportedPriceCents,
            )) {
                is ApiResult.Success -> {
                    applyMenuItemUpdate(result.data.menuItemUpdated)
                    emit(DetailEvent.Toast("Reported. Thanks for keeping prices honest."))
                }
                is ApiResult.HttpError -> emit(DetailEvent.Toast("Couldn't report (error ${result.code})"))
                is ApiResult.NetworkError -> emit(DetailEvent.Toast("Network error — try again"))
            }
            markConfirming(menuItemId, false)
        }
    }

    fun reportMenu(menuItemId: String, reason: ReportReason, comment: String?) {
        viewModelScope.launch {
            when (val result = submissionRepo.report(menuItemId, reason, comment?.takeIf { it.isNotBlank() })) {
                is ApiResult.Success -> {
                    if (result.data.menuItemAutoDisputed) {
                        updateMenuItemStatus(menuItemId, VerificationStatus.DISPUTED)
                    }
                    emit(DetailEvent.Toast("Thanks for reporting. We'll review."))
                }
                is ApiResult.HttpError -> emit(DetailEvent.Toast("Couldn't submit report (error ${result.code})"))
                is ApiResult.NetworkError -> emit(DetailEvent.Toast("Network error — try again"))
            }
        }
    }

    fun rateRestaurant(score: Int, comment: String?) {
        viewModelScope.launch {
            when (val result = meRepo.rate(restaurantId, score, comment?.takeIf { it.isNotBlank() })) {
                is ApiResult.Success -> emit(DetailEvent.Toast("Rating submitted. Thanks!"))
                is ApiResult.HttpError -> emit(
                    DetailEvent.Toast(
                        if (result.code == 403) "You need Level 3 to rate"
                        else "Couldn't submit rating (error ${result.code})",
                    ),
                )
                is ApiResult.NetworkError -> emit(DetailEvent.Toast("Network error — try again"))
            }
        }
    }

    private fun markConfirming(menuItemId: String, on: Boolean) {
        val current = _state.value.confirmingIds
        _state.value = _state.value.copy(
            confirmingIds = if (on) current + menuItemId else current - menuItemId,
        )
    }

    private fun applyMenuItemUpdate(update: com.brokenlunch.gr.data.model.MenuItemUpdate) {
        val r = _state.value.restaurant ?: return
        val updatedMenu = r.menu.copy(
            survive = updateList(r.menu.survive, update),
            costEffective = updateList(r.menu.costEffective, update),
            luxury = updateList(r.menu.luxury, update),
        )
        _state.value = _state.value.copy(restaurant = r.copy(menu = updatedMenu))
    }

    private fun updateMenuItemStatus(menuItemId: String, status: VerificationStatus) {
        val r = _state.value.restaurant ?: return
        fun patch(list: List<MenuItem>) = list.map {
            if (it.id == menuItemId) it.copy(verificationStatus = status) else it
        }
        val updatedMenu = r.menu.copy(
            survive = patch(r.menu.survive),
            costEffective = patch(r.menu.costEffective),
            luxury = patch(r.menu.luxury),
        )
        _state.value = _state.value.copy(restaurant = r.copy(menu = updatedMenu))
    }

    private fun updateList(
        list: List<MenuItem>,
        update: com.brokenlunch.gr.data.model.MenuItemUpdate,
    ): List<MenuItem> = list.map { item ->
        if (item.id == update.id) {
            item.copy(
                verificationStatus = update.verificationStatus,
                confirmationCount = update.confirmationCount,
            )
        } else item
    }

    private suspend fun emit(e: DetailEvent) {
        _events.emit(e)
    }

    fun tieredMenu(detail: RestaurantDetail): List<Pair<Tier, List<MenuItem>>> = buildList {
        if (detail.menu.survive.isNotEmpty()) add(Tier.SURVIVE to detail.menu.survive)
        if (detail.menu.costEffective.isNotEmpty()) add(Tier.COST_EFFECTIVE to detail.menu.costEffective)
        if (detail.menu.luxury.isNotEmpty()) add(Tier.LUXURY to detail.menu.luxury)
    }
}
