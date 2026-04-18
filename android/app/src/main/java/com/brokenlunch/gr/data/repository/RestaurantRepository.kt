package com.brokenlunch.gr.data.repository

import com.brokenlunch.gr.data.api.BrokenLunchApi
import com.brokenlunch.gr.data.model.NearbyResponse
import com.brokenlunch.gr.data.model.RestaurantDetail
import com.brokenlunch.gr.data.model.Tier
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class RestaurantRepository @Inject constructor(
    private val api: BrokenLunchApi,
) {
    suspend fun nearby(
        lat: Double,
        lng: Double,
        radiusM: Int = 2000,
        tier: Tier? = null,
        verifiedOnly: Boolean = false,
        includeEmpty: Boolean = true,
        limit: Int = 100,
    ): Result<NearbyResponse> = runCatching {
        api.getNearby(
            lat = lat,
            lng = lng,
            radiusM = radiusM,
            tier = tier?.let { tierToWire(it) },
            verifiedOnly = verifiedOnly,
            includeEmpty = includeEmpty,
            limit = limit,
        )
    }

    suspend fun detail(id: String): Result<RestaurantDetail> = runCatching {
        api.getRestaurant(id)
    }

    private fun tierToWire(tier: Tier): String = when (tier) {
        Tier.SURVIVE -> "survive"
        Tier.COST_EFFECTIVE -> "cost_effective"
        Tier.LUXURY -> "luxury"
    }
}
