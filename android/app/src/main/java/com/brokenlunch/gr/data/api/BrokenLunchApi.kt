package com.brokenlunch.gr.data.api

import com.brokenlunch.gr.data.model.ConfirmationRequest
import com.brokenlunch.gr.data.model.ConfirmationResponse
import com.brokenlunch.gr.data.model.MeResponse
import com.brokenlunch.gr.data.model.NearbyResponse
import com.brokenlunch.gr.data.model.ParsedMenuResponse
import com.brokenlunch.gr.data.model.RatingRequest
import com.brokenlunch.gr.data.model.RatingResponse
import com.brokenlunch.gr.data.model.RecommendRequest
import com.brokenlunch.gr.data.model.RecommendResponse
import com.brokenlunch.gr.data.model.ReportRequest
import com.brokenlunch.gr.data.model.ReportResponse
import com.brokenlunch.gr.data.model.RestaurantDetail
import com.brokenlunch.gr.data.model.SubmissionRequest
import com.brokenlunch.gr.data.model.SubmissionResponse
import okhttp3.MultipartBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

interface BrokenLunchApi {

    @GET("restaurants/nearby")
    suspend fun getNearby(
        @Query("lat") lat: Double,
        @Query("lng") lng: Double,
        @Query("radius_m") radiusM: Int = 2000,
        @Query("tier") tier: String? = null,
        @Query("verified_only") verifiedOnly: Boolean = false,
        @Query("include_empty") includeEmpty: Boolean = true,
        @Query("limit") limit: Int = 100,
    ): NearbyResponse

    @GET("restaurants/{id}")
    suspend fun getRestaurant(@Path("id") id: String): RestaurantDetail

    @POST("submissions")
    suspend fun postSubmission(@Body body: SubmissionRequest): SubmissionResponse

    @POST("confirmations")
    suspend fun postConfirmation(@Body body: ConfirmationRequest): ConfirmationResponse

    @Multipart
    @POST("parse-menu-image")
    suspend fun parseMenuImage(@Part image: MultipartBody.Part): ParsedMenuResponse

    @POST("recommend")
    suspend fun postRecommend(@Body body: RecommendRequest): RecommendResponse

    @POST("reports")
    suspend fun postReport(@Body body: ReportRequest): ReportResponse

    @POST("ratings")
    suspend fun postRating(@Body body: RatingRequest): RatingResponse

    @GET("me")
    suspend fun getMe(): MeResponse
}
