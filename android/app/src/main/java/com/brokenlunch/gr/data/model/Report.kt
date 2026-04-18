package com.brokenlunch.gr.data.model

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class ReportRequest(
    @Json(name = "menu_item_id") val menuItemId: String,
    @Json(name = "reason") val reason: ReportReason,
    @Json(name = "comment") val comment: String? = null,
)

@JsonClass(generateAdapter = true)
data class ReportResponse(
    @Json(name = "id") val id: String,
    @Json(name = "status") val status: String,
    @Json(name = "menu_item_auto_disputed") val menuItemAutoDisputed: Boolean,
)
