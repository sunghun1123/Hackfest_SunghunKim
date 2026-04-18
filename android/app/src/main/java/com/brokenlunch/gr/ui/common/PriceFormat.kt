package com.brokenlunch.gr.ui.common

fun formatPriceCents(priceCents: Int): String {
    val dollars = priceCents / 100
    val cents = priceCents % 100
    return "$%d.%02d".format(dollars, cents)
}

fun formatDistanceMeters(distanceM: Int): String {
    val miles = distanceM / 1609.344
    return if (miles < 0.1) "${distanceM} m" else "%.1f mi".format(miles)
}
