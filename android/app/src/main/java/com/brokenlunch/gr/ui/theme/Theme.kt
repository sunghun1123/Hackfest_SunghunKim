package com.brokenlunch.gr.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

private val LightColors = lightColorScheme(
    primary = SurviveBorder,
    onPrimary = androidx.compose.ui.graphics.Color.White,
    secondary = CostBorder,
    error = LuxuryBorder,
)

@Composable
fun BrokenLunchTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = LightColors,
        content = content,
    )
}
