package com.brokenlunch.gr.ui.map

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.brokenlunch.gr.data.model.Tier
import com.brokenlunch.gr.ui.theme.CostBg
import com.brokenlunch.gr.ui.theme.CostBorder
import com.brokenlunch.gr.ui.theme.CostText
import com.brokenlunch.gr.ui.theme.EmptyBg
import com.brokenlunch.gr.ui.theme.EmptyBorder
import com.brokenlunch.gr.ui.theme.EmptyIcon
import com.brokenlunch.gr.ui.theme.EmptyText
import com.brokenlunch.gr.ui.theme.LuxuryBg
import com.brokenlunch.gr.ui.theme.LuxuryBorder
import com.brokenlunch.gr.ui.theme.LuxuryText
import com.brokenlunch.gr.ui.theme.SurviveBg
import com.brokenlunch.gr.ui.theme.SurviveBorder
import com.brokenlunch.gr.ui.theme.SurviveText

private data class TierPalette(val bg: Color, val border: Color, val text: Color)

private fun palette(tier: Tier): TierPalette = when (tier) {
    Tier.SURVIVE -> TierPalette(SurviveBg, SurviveBorder, SurviveText)
    Tier.COST_EFFECTIVE -> TierPalette(CostBg, CostBorder, CostText)
    Tier.LUXURY -> TierPalette(LuxuryBg, LuxuryBorder, LuxuryText)
}

private fun formatPrice(priceCents: Int): String {
    val dollars = priceCents / 100
    val cents = priceCents % 100
    return "$%d.%02d".format(dollars, cents)
}

private val PinCorner = 14.dp
private val PinShape = RoundedCornerShape(PinCorner)
private val PinHeight = 28.dp
private val BorderWidth = 1.5.dp

@Composable
private fun PinShell(
    bg: Color,
    borderModifier: Modifier,
    content: @Composable () -> Unit,
) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .height(PinHeight)
            .clip(PinShape)
            .background(bg, PinShape)
            .then(borderModifier)
            .padding(start = 3.dp, end = 10.dp, top = 3.dp, bottom = 3.dp),
        content = { content() },
    )
}

@Composable
private fun IconCircle(content: @Composable () -> Unit) {
    Box(
        modifier = Modifier
            .size(22.dp)
            .clip(CircleShape)
            .background(Color.White, CircleShape),
        contentAlignment = Alignment.Center,
    ) { content() }
}

@Composable
fun PopulatedVerifiedPin(tier: Tier, priceCents: Int, category: String?) {
    val p = palette(tier)
    PinShell(
        bg = p.bg,
        borderModifier = Modifier.border(BorderWidth, p.border, PinShape),
    ) {
        IconCircle { Text(categoryEmoji(category), fontSize = 12.sp) }
        Spacer(Modifier.width(5.dp))
        Text(
            text = formatPrice(priceCents),
            color = p.text,
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium,
        )
    }
}

@Composable
fun PopulatedAiPin(tier: Tier, priceCents: Int, category: String?) {
    val p = palette(tier)
    val dashed = Modifier.drawBehind {
        val stroke = BorderWidth.toPx()
        val radius = PinCorner.toPx()
        drawRoundRect(
            color = p.border,
            topLeft = Offset(stroke / 2, stroke / 2),
            size = Size(size.width - stroke, size.height - stroke),
            cornerRadius = CornerRadius(radius, radius),
            style = Stroke(
                width = stroke,
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(9f, 6f), 0f),
            ),
        )
    }
    PinShell(bg = p.bg, borderModifier = dashed) {
        IconCircle { Text(categoryEmoji(category), fontSize = 12.sp) }
        Spacer(Modifier.width(5.dp))
        Text(
            text = formatPrice(priceCents),
            color = p.text,
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium,
        )
    }
}

@Composable
fun EmptyPin() {
    PinShell(
        bg = EmptyBg,
        borderModifier = Modifier.border(BorderWidth, EmptyBorder, PinShape),
    ) {
        IconCircle {
            Text("?", color = EmptyIcon, fontSize = 12.sp, fontWeight = FontWeight.Medium)
        }
        Spacer(Modifier.width(5.dp))
        Text(
            text = "+15 pts",
            color = EmptyText,
            fontSize = 11.sp,
            fontWeight = FontWeight.Medium,
        )
    }
}
