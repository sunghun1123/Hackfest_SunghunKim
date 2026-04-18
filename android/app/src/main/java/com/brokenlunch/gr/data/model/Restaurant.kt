package com.brokenlunch.gr.data.model

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class RestaurantNearby(
    @Json(name = "id") val id: String,
    @Json(name = "name") val name: String,
    @Json(name = "category") val category: String?,
    @Json(name = "lat") val lat: Double,
    @Json(name = "lng") val lng: Double,
    @Json(name = "distance_m") val distanceM: Int,
    @Json(name = "google_rating") val googleRating: Double?,
    @Json(name = "app_rating") val appRating: Double?,
    @Json(name = "menu_status") val menuStatus: MenuStatus,
    @Json(name = "cheapest_menu") val cheapestMenu: CheapestMenu?,
)

@JsonClass(generateAdapter = true)
data class CheapestMenu(
    @Json(name = "id") val id: String,
    @Json(name = "name") val name: String,
    @Json(name = "price_cents") val priceCents: Int,
    @Json(name = "tier") val tier: Tier,
    @Json(name = "verification_status") val verificationStatus: VerificationStatus,
)

@JsonClass(generateAdapter = true)
data class NearbyResponse(
    @Json(name = "restaurants") val restaurants: List<RestaurantNearby>,
    @Json(name = "count") val count: Int,
)

@JsonClass(generateAdapter = true)
data class RestaurantDetail(
    @Json(name = "id") val id: String,
    @Json(name = "name") val name: String,
    @Json(name = "address") val address: String?,
    @Json(name = "phone") val phone: String?,
    @Json(name = "website") val website: String?,
    @Json(name = "lat") val lat: Double,
    @Json(name = "lng") val lng: Double,
    @Json(name = "google_rating") val googleRating: Double?,
    @Json(name = "app_rating") val appRating: Double?,
    @Json(name = "rating_count") val ratingCount: Int,
    @Json(name = "menu") val menu: MenuByTier,
)

@JsonClass(generateAdapter = true)
data class MenuByTier(
    @Json(name = "survive") val survive: List<MenuItem> = emptyList(),
    @Json(name = "cost_effective") val costEffective: List<MenuItem> = emptyList(),
    @Json(name = "luxury") val luxury: List<MenuItem> = emptyList(),
) {
    fun isEmpty(): Boolean = survive.isEmpty() && costEffective.isEmpty() && luxury.isEmpty()
}
