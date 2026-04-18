package com.brokenlunch.gr.data.model

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class MenuItem(
    @Json(name = "id") val id: String,
    @Json(name = "name") val name: String,
    @Json(name = "description") val description: String?,
    @Json(name = "price_cents") val priceCents: Int,
    @Json(name = "photo_url") val photoUrl: String?,
    @Json(name = "verification_status") val verificationStatus: VerificationStatus,
    @Json(name = "confirmation_count") val confirmationCount: Int,
    @Json(name = "source") val source: String,
    @Json(name = "last_verified_at") val lastVerifiedAt: String?,
)
