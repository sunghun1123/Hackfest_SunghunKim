package com.brokenlunch.gr.data.model

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class MeResponse(
    @Json(name = "device_id") val deviceId: String,
    @Json(name = "display_name") val displayName: String?,
    @Json(name = "points") val points: Int,
    @Json(name = "level") val level: Int,
    @Json(name = "level_name") val levelName: String,
    @Json(name = "level_weight") val levelWeight: Int,
    @Json(name = "next_level_points") val nextLevelPoints: Int?,
    @Json(name = "submission_count") val submissionCount: Int,
    @Json(name = "confirmation_count") val confirmationCount: Int,
    @Json(name = "daily_streak") val dailyStreak: Int,
    @Json(name = "can_rate_restaurants") val canRateRestaurants: Boolean,
    @Json(name = "first_seen") val firstSeen: String,
)
