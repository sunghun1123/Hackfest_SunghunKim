package com.brokenlunch.gr.data.model

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class SubmissionRequest(
    @Json(name = "restaurant_id") val restaurantId: String,
    @Json(name = "menu_name") val menuName: String,
    @Json(name = "price_cents") val priceCents: Int,
    @Json(name = "photo_url") val photoUrl: String? = null,
    @Json(name = "gemini_parsed") val geminiParsed: GeminiParsedInfo? = null,
    @Json(name = "source") val source: String,
)

@JsonClass(generateAdapter = true)
data class GeminiParsedInfo(
    @Json(name = "confidence") val confidence: Double,
    @Json(name = "raw_text") val rawText: String? = null,
)

@JsonClass(generateAdapter = true)
data class SubmissionResponse(
    @Json(name = "id") val id: String,
    @Json(name = "menu_item_id") val menuItemId: String,
    @Json(name = "status") val status: String,
    @Json(name = "points_awarded") val pointsAwarded: Int,
    @Json(name = "is_first_submission") val isFirstSubmission: Boolean,
    @Json(name = "bonus_message") val bonusMessage: String? = null,
    @Json(name = "user_total_points") val userTotalPoints: Int,
    @Json(name = "user_level") val userLevel: Int,
    @Json(name = "level_up") val levelUp: Boolean,
)
