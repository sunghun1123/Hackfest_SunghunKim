package com.brokenlunch.gr.data.repository

import com.brokenlunch.gr.data.api.BrokenLunchApi
import com.brokenlunch.gr.data.model.ParsedMenuResponse
import com.brokenlunch.gr.data.model.RecommendRequest
import com.brokenlunch.gr.data.model.RecommendResponse
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class GeminiRepository @Inject constructor(
    private val api: BrokenLunchApi,
) {
    suspend fun parseMenuImage(imageBytes: ByteArray, mimeType: String = "image/jpeg"): Result<ParsedMenuResponse> = runCatching {
        val part = MultipartBody.Part.createFormData(
            name = "image",
            filename = "menu.jpg",
            body = imageBytes.toRequestBody(mimeType.toMediaTypeOrNull()),
        )
        api.parseMenuImage(part)
    }

    suspend fun recommend(lat: Double, lng: Double, query: String, maxResults: Int = 5): Result<RecommendResponse> = runCatching {
        api.postRecommend(RecommendRequest(lat, lng, query, maxResults))
    }
}
