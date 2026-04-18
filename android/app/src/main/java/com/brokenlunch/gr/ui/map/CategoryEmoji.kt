package com.brokenlunch.gr.ui.map

fun categoryEmoji(category: String?): String = when (category?.lowercase()) {
    "pizza" -> "\uD83C\uDF55"
    "burger" -> "\uD83C\uDF54"
    "mexican" -> "\uD83C\uDF2E"
    "asian" -> "\uD83C\uDF5C"
    "sandwich" -> "\uD83E\uDD6A"
    "coffee" -> "\u2615"
    "bakery" -> "\uD83E\uDD50"
    "mediterranean" -> "\uD83E\uDD59"
    "breakfast" -> "\uD83C\uDF73"
    "chicken" -> "\uD83C\uDF57"
    "dessert" -> "\uD83C\uDF70"
    else -> "\uD83C\uDF74"
}
