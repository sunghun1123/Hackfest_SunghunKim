package com.brokenlunch.gr.data.model

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = false)
enum class VerificationStatus {
    @Json(name = "ai_parsed") AI_PARSED,
    @Json(name = "human_verified") HUMAN_VERIFIED,
    @Json(name = "disputed") DISPUTED,
    @Json(name = "needs_verification") NEEDS_VERIFICATION,
}

@JsonClass(generateAdapter = false)
enum class Tier {
    @Json(name = "survive") SURVIVE,
    @Json(name = "cost_effective") COST_EFFECTIVE,
    @Json(name = "luxury") LUXURY,
}

@JsonClass(generateAdapter = false)
enum class MenuStatus {
    @Json(name = "populated_verified") POPULATED_VERIFIED,
    @Json(name = "populated_ai") POPULATED_AI,
    @Json(name = "empty") EMPTY,
}

@JsonClass(generateAdapter = false)
enum class ReportReason {
    @Json(name = "wrong_price") WRONG_PRICE,
    @Json(name = "not_on_menu") NOT_ON_MENU,
    @Json(name = "spam") SPAM,
    @Json(name = "inappropriate") INAPPROPRIATE,
    @Json(name = "other") OTHER,
}
