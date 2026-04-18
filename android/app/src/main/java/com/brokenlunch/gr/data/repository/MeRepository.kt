package com.brokenlunch.gr.data.repository

import com.brokenlunch.gr.data.ApiResult
import com.brokenlunch.gr.data.api.BrokenLunchApi
import com.brokenlunch.gr.data.model.MeResponse
import com.brokenlunch.gr.data.model.RatingRequest
import com.brokenlunch.gr.data.model.RatingResponse
import com.brokenlunch.gr.data.safeApiCall
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class MeRepository @Inject constructor(
    private val api: BrokenLunchApi,
) {
    suspend fun me(): ApiResult<MeResponse> = safeApiCall {
        api.getMe()
    }

    suspend fun rate(restaurantId: String, score: Int, comment: String? = null): ApiResult<RatingResponse> = safeApiCall {
        api.postRating(RatingRequest(restaurantId, score, comment))
    }
}
