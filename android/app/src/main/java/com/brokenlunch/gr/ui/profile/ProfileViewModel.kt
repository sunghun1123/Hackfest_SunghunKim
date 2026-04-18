package com.brokenlunch.gr.ui.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.brokenlunch.gr.data.ApiResult
import com.brokenlunch.gr.data.model.MeResponse
import com.brokenlunch.gr.data.repository.MeRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

enum class ProfileStage { LOADING, SUCCESS, ERROR }

data class ProfileUiState(
    val stage: ProfileStage = ProfileStage.LOADING,
    val me: MeResponse? = null,
    val error: String? = null,
)

// Floors matching backend _NEXT_LEVEL_THRESHOLDS. Index = level - 1.
private val LEVEL_FLOORS = intArrayOf(0, 50, 150, 400, 1000, 2500, 2500, 10_000, 10_000, 10_000)

fun currentLevelFloor(level: Int): Int {
    val idx = (level - 1).coerceIn(0, LEVEL_FLOORS.lastIndex)
    return LEVEL_FLOORS[idx]
}

/** Returns 0f..1f progress within current level, or 1f at max level. */
fun levelProgress(points: Int, level: Int, nextLevelPoints: Int?): Float {
    if (nextLevelPoints == null || nextLevelPoints <= 0) return 1f
    val floor = currentLevelFloor(level)
    val span = (nextLevelPoints - floor).coerceAtLeast(1)
    return ((points - floor).toFloat() / span).coerceIn(0f, 1f)
}

@HiltViewModel
class ProfileViewModel @Inject constructor(
    private val meRepo: MeRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(ProfileUiState())
    val state: StateFlow<ProfileUiState> = _state.asStateFlow()

    init {
        load()
    }

    fun load() {
        _state.value = _state.value.copy(stage = ProfileStage.LOADING, error = null)
        viewModelScope.launch {
            when (val r = meRepo.me()) {
                is ApiResult.Success -> _state.value = _state.value.copy(
                    stage = ProfileStage.SUCCESS,
                    me = r.data,
                )
                is ApiResult.HttpError -> _state.value = _state.value.copy(
                    stage = ProfileStage.ERROR,
                    error = "Couldn't load profile (error ${r.code}).",
                )
                is ApiResult.NetworkError -> _state.value = _state.value.copy(
                    stage = ProfileStage.ERROR,
                    error = "Can't reach server — check your connection.",
                )
            }
        }
    }
}
