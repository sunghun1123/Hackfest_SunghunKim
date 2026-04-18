package com.brokenlunch.gr.data.model

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class RatingRequest(
    @Json(name = "restaurant_id") val restaurantId: String,
    @Json(name = "score") val score: Int,
    @Json(name = "comment") val comment: String? = null,
)

@JsonClass(generateAdapter = true)
data class RatingResponse(
    @Json(name = "id") val id: String,
    @Json(name = "restaurant_updated") val restaurantUpdated: RestaurantRatingUpdate,
    @Json(name = "points_awarded") val pointsAwarded: Int,
)

@JsonClass(generateAdapter = true)
data class RestaurantRatingUpdate(
    @Json(name = "id") val id: String,
    @Json(name = "app_rating") val appRating: Double,
    @Json(name = "rating_count") val ratingCount: Int,
)
