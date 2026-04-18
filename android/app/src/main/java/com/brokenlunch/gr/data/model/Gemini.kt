package com.brokenlunch.gr.data.model

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class ParsedMenuResponse(
    @Json(name = "items") val items: List<ParsedMenuItem>,
    @Json(name = "warnings") val warnings: List<String> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class ParsedMenuItem(
    @Json(name = "name") val name: String,
    @Json(name = "price_cents") val priceCents: Int,
    @Json(name = "description") val description: String? = null,
    @Json(name = "confidence") val confidence: Double,
)

@JsonClass(generateAdapter = true)
data class RecommendRequest(
    @Json(name = "lat") val lat: Double,
    @Json(name = "lng") val lng: Double,
    @Json(name = "query") val query: String,
    @Json(name = "max_results") val maxResults: Int = 5,
)

@JsonClass(generateAdapter = true)
data class RecommendResponse(
    @Json(name = "recommendations") val recommendations: List<Recommendation>,
)

@JsonClass(generateAdapter = true)
data class Recommendation(
    @Json(name = "restaurant_id") val restaurantId: String,
    @Json(name = "restaurant_name") val restaurantName: String,
    @Json(name = "menu_item_id") val menuItemId: String,
    @Json(name = "menu_name") val menuName: String,
    @Json(name = "price_cents") val priceCents: Int,
    @Json(name = "distance_m") val distanceM: Int,
    @Json(name = "verification_status") val verificationStatus: VerificationStatus,
    @Json(name = "reason") val reason: String,
)
