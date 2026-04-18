package com.brokenlunch.gr.data.model

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class ConfirmationRequest(
    @Json(name = "menu_item_id") val menuItemId: String,
    @Json(name = "is_agreement") val isAgreement: Boolean,
    @Json(name = "reported_price") val reportedPrice: Int? = null,
)

@JsonClass(generateAdapter = true)
data class ConfirmationResponse(
    @Json(name = "id") val id: String,
    @Json(name = "menu_item_updated") val menuItemUpdated: MenuItemUpdate,
    @Json(name = "points_awarded") val pointsAwarded: Int,
    @Json(name = "user_total_points") val userTotalPoints: Int,
)

@JsonClass(generateAdapter = true)
data class MenuItemUpdate(
    @Json(name = "id") val id: String,
    @Json(name = "verification_status") val verificationStatus: VerificationStatus,
    @Json(name = "confirmation_weight") val confirmationWeight: Int,
    @Json(name = "confirmation_count") val confirmationCount: Int,
)
