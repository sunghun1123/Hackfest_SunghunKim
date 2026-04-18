package com.brokenlunch.gr.ui.common

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.brokenlunch.gr.data.model.VerificationStatus
import com.brokenlunch.gr.ui.theme.AiParsedBg
import com.brokenlunch.gr.ui.theme.AiParsedText
import com.brokenlunch.gr.ui.theme.DisputedBg
import com.brokenlunch.gr.ui.theme.DisputedText
import com.brokenlunch.gr.ui.theme.HumanVerifiedBg
import com.brokenlunch.gr.ui.theme.HumanVerifiedText
import com.brokenlunch.gr.ui.theme.NeedsVerificationText

@Composable
fun VerificationBadge(
    status: VerificationStatus,
    modifier: Modifier = Modifier,
) {
    if (status == VerificationStatus.NEEDS_VERIFICATION) {
        Text(
            text = "needs verification",
            fontSize = 10.sp,
            fontWeight = FontWeight.Medium,
            color = NeedsVerificationText,
            modifier = modifier,
        )
        return
    }
    val (bg, fg, label, icon) = when (status) {
        VerificationStatus.HUMAN_VERIFIED -> BadgeSpec(HumanVerifiedBg, HumanVerifiedText, "Human verified", Icons.Default.Check)
        VerificationStatus.AI_PARSED -> BadgeSpec(AiParsedBg, AiParsedText, "AI parsed", Icons.Default.Star)
        VerificationStatus.DISPUTED -> BadgeSpec(DisputedBg, DisputedText, "Disputed", Icons.Default.Warning)
        VerificationStatus.NEEDS_VERIFICATION -> error("unreachable")
    }
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = modifier
            .height(16.dp)
            .clip(RoundedCornerShape(999.dp))
            .background(bg)
            .padding(horizontal = 8.dp, vertical = 2.dp),
    ) {
        Icon(
            imageVector = icon,
            contentDescription = "$label price",
            tint = fg,
            modifier = Modifier.height(10.dp),
        )
        Spacer(Modifier.width(3.dp))
        Text(label, fontSize = 10.sp, fontWeight = FontWeight.Medium, color = fg)
    }
}

private data class BadgeSpec(
    val bg: androidx.compose.ui.graphics.Color,
    val fg: androidx.compose.ui.graphics.Color,
    val label: String,
    val icon: androidx.compose.ui.graphics.vector.ImageVector,
)
