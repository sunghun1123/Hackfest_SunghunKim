package com.brokenlunch.gr.data.model

import com.squareup.moshi.Moshi
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DtoParsingTest {

    private val moshi: Moshi = Moshi.Builder().build()

    @Test
    fun parsesNearbyResponseWithBothPopulatedAndEmpty() {
        val json = """
            {
              "restaurants": [
                {
                  "id": "r1",
                  "name": "Jet's Pizza",
                  "category": "pizza",
                  "lat": 42.9634,
                  "lng": -85.6681,
                  "distance_m": 320,
                  "google_rating": 4.3,
                  "app_rating": 4.5,
                  "menu_status": "populated_verified",
                  "cheapest_menu": {
                    "id": "m1",
                    "name": "8-corner slice",
                    "price_cents": 450,
                    "tier": "survive",
                    "verification_status": "human_verified"
                  }
                },
                {
                  "id": "r2",
                  "name": "Corner Deli",
                  "category": "sandwich",
                  "lat": 42.9534,
                  "lng": -85.6581,
                  "distance_m": 450,
                  "google_rating": 4.1,
                  "app_rating": null,
                  "menu_status": "empty",
                  "cheapest_menu": null
                }
              ],
              "count": 2
            }
        """.trimIndent()

        val adapter = moshi.adapter(NearbyResponse::class.java)
        val parsed = adapter.fromJson(json)!!

        assertEquals(2, parsed.count)
        assertEquals(2, parsed.restaurants.size)

        val populated = parsed.restaurants[0]
        assertEquals("Jet's Pizza", populated.name)
        assertEquals(MenuStatus.POPULATED_VERIFIED, populated.menuStatus)
        assertNotNull(populated.cheapestMenu)
        assertEquals(Tier.SURVIVE, populated.cheapestMenu!!.tier)
        assertEquals(VerificationStatus.HUMAN_VERIFIED, populated.cheapestMenu!!.verificationStatus)
        assertEquals(450, populated.cheapestMenu!!.priceCents)
        assertEquals(4.5, populated.appRating!!, 0.001)

        val empty = parsed.restaurants[1]
        assertEquals(MenuStatus.EMPTY, empty.menuStatus)
        assertNull(empty.cheapestMenu)
        assertNull(empty.appRating)
    }

    @Test
    fun parsesRestaurantDetailWithTierBuckets() {
        val json = """
            {
              "id": "r1",
              "name": "Pita House",
              "address": "456 Division Ave, Grand Rapids, MI",
              "phone": "+1-616-555-0123",
              "website": "https://pitahouse.com",
              "lat": 42.9534,
              "lng": -85.6681,
              "google_rating": 4.5,
              "app_rating": 4.2,
              "rating_count": 23,
              "menu": {
                "survive": [
                  {
                    "id": "m1",
                    "name": "Falafel 2p",
                    "description": "two pieces with sauce",
                    "price_cents": 399,
                    "photo_url": null,
                    "verification_status": "human_verified",
                    "confirmation_count": 5,
                    "source": "gemini_web",
                    "last_verified_at": "2026-04-15T10:23:00Z"
                  }
                ],
                "cost_effective": [],
                "luxury": []
              }
            }
        """.trimIndent()

        val adapter = moshi.adapter(RestaurantDetail::class.java)
        val parsed = adapter.fromJson(json)!!

        assertEquals("Pita House", parsed.name)
        assertEquals(1, parsed.menu.survive.size)
        assertTrue(parsed.menu.costEffective.isEmpty())
        assertEquals(VerificationStatus.HUMAN_VERIFIED, parsed.menu.survive[0].verificationStatus)
    }

    @Test
    fun parsesSubmissionResponseWithFirstSubmissionBonus() {
        val json = """
            {
              "id": "s1",
              "menu_item_id": "m1",
              "status": "accepted",
              "points_awarded": 15,
              "is_first_submission": true,
              "bonus_message": "First to register this restaurant! +5 bonus",
              "user_total_points": 240,
              "user_level": 3,
              "level_up": false
            }
        """.trimIndent()

        val parsed = moshi.adapter(SubmissionResponse::class.java).fromJson(json)!!
        assertEquals(15, parsed.pointsAwarded)
        assertTrue(parsed.isFirstSubmission)
        assertEquals(3, parsed.userLevel)
    }

    @Test
    fun parsesParsedMenuResponseFromGemini() {
        val json = """
            {
              "items": [
                {"name": "Hummus pita", "price_cents": 450, "description": "with tahini sauce", "confidence": 0.95},
                {"name": "Falafel wrap", "price_cents": 699, "description": null, "confidence": 0.88}
              ],
              "warnings": []
            }
        """.trimIndent()

        val parsed = moshi.adapter(ParsedMenuResponse::class.java).fromJson(json)!!
        assertEquals(2, parsed.items.size)
        assertEquals(450, parsed.items[0].priceCents)
        assertEquals(0.95, parsed.items[0].confidence, 0.001)
    }

    @Test
    fun parsesMeResponse() {
        val json = """
            {
              "device_id": "d1",
              "display_name": null,
              "points": 235,
              "level": 3,
              "level_name": "Regular",
              "level_weight": 1,
              "next_level_points": 400,
              "submission_count": 12,
              "confirmation_count": 18,
              "daily_streak": 3,
              "can_rate_restaurants": true,
              "first_seen": "2026-04-15T10:00:00Z"
            }
        """.trimIndent()

        val parsed = moshi.adapter(MeResponse::class.java).fromJson(json)!!
        assertEquals(3, parsed.level)
        assertEquals("Regular", parsed.levelName)
        assertTrue(parsed.canRateRestaurants)
    }
}
