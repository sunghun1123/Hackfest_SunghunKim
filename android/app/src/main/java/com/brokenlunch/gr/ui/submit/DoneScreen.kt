package com.brokenlunch.gr.ui.submit

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.brokenlunch.gr.ui.theme.HumanVerifiedBg
import com.brokenlunch.gr.ui.theme.HumanVerifiedText
import com.brokenlunch.gr.ui.theme.SurviveBorder

@Composable
fun DoneScreen(
    result: SubmitResult,
    onDoneBack: () -> Unit,
    onSubmitMore: () -> Unit,
) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
    ) {
        Box(
            modifier = Modifier
                .size(96.dp)
                .clip(CircleShape)
                .background(HumanVerifiedBg),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                Icons.Default.Check,
                contentDescription = null,
                tint = HumanVerifiedText,
                modifier = Modifier.size(56.dp),
            )
        }
        Spacer(Modifier.height(20.dp))
        Text(
            "Thanks for sharing!",
            fontSize = 20.sp,
            fontWeight = FontWeight.Medium,
        )
        Spacer(Modifier.height(8.dp))
        if (result.successCount > 0) {
            Text(
                "You earned +${result.totalPoints} points",
                fontSize = 16.sp,
                fontWeight = FontWeight.Medium,
                color = SurviveBorder,
            )
        }
        if (result.firstSubmissionBonuses > 0) {
            Spacer(Modifier.height(4.dp))
            Text(
                "${result.firstSubmissionBonuses} first-submission bonus${if (result.firstSubmissionBonuses == 1) "" else "es"}",
                fontSize = 13.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (result.levelUp) {
            Spacer(Modifier.height(8.dp))
            Box(
                modifier = Modifier
                    .clip(androidx.compose.foundation.shape.RoundedCornerShape(999.dp))
                    .background(SurviveBorder)
                    .padding(horizontal = 14.dp, vertical = 6.dp),
            ) {
                Text(
                    "Level up! You're now Level ${result.finalLevel}",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    color = Color.White,
                )
            }
        }
        if (result.failureCount > 0) {
            Spacer(Modifier.height(12.dp))
            Text(
                "${result.failureCount} item${if (result.failureCount == 1) "" else "s"} failed to submit",
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.error,
            )
        }
        Spacer(Modifier.height(32.dp))
        Button(
            onClick = onDoneBack,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Done", fontSize = 14.sp)
        }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(
            onClick = onSubmitMore,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Submit more", fontSize = 14.sp)
        }
    }
}
