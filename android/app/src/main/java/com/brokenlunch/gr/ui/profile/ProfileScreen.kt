package com.brokenlunch.gr.ui.profile

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.EmojiEvents
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.LocalFireDepartment
import androidx.compose.material.icons.filled.Restaurant
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.Verified
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.brokenlunch.gr.data.model.MeResponse
import com.brokenlunch.gr.ui.theme.SurviveBg
import com.brokenlunch.gr.ui.theme.SurviveBorder
import com.brokenlunch.gr.ui.theme.SurviveText

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfileScreen(
    vm: ProfileViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(title = { Text("Profile", fontWeight = FontWeight.Medium) })
        },
    ) { inner ->
        Box(
            Modifier
                .fillMaxSize()
                .padding(inner),
        ) {
            when (state.stage) {
                ProfileStage.LOADING -> LoadingState()
                ProfileStage.ERROR -> ErrorState(
                    message = state.error ?: "Something went wrong.",
                    onRetry = vm::load,
                )
                ProfileStage.SUCCESS -> state.me?.let { ProfileContent(it) }
            }
        }
    }
}

@Composable
private fun LoadingState() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        CircularProgressIndicator()
    }
}

@Composable
private fun ErrorState(message: String, onRetry: () -> Unit) {
    Column(
        Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(message, fontSize = 14.sp, fontWeight = FontWeight.Medium)
        Spacer(Modifier.height(12.dp))
        FilledTonalButton(onClick = onRetry) {
            Text("Try again", fontSize = 13.sp)
        }
    }
}

@Composable
private fun ProfileContent(me: MeResponse) {
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        HeaderCard(me)
        StatsGrid(me)
        DailyBonusBanner(streak = me.dailyStreak)
        PerksCard(level = me.level, canRate = me.canRateRestaurants, levelWeight = me.levelWeight)
    }
}

@Composable
private fun HeaderCard(me: MeResponse) {
    val progress = levelProgress(me.points, me.level, me.nextLevelPoints)
    val isMaxLevel = (me.nextLevelPoints ?: -1) <= 0

    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(SurviveBg)
            .border(1.dp, SurviveBorder, RoundedCornerShape(16.dp))
            .padding(20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            Modifier
                .size(72.dp)
                .clip(CircleShape)
                .background(SurviveBorder),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                me.level.toString(),
                fontSize = 28.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onPrimary,
            )
        }
        Spacer(Modifier.height(10.dp))
        Text(
            me.displayName?.takeIf { it.isNotBlank() } ?: "Anonymous eater",
            fontSize = 18.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            "Level ${me.level} · ${me.levelName}",
            fontSize = 13.sp,
            color = SurviveText,
        )
        Spacer(Modifier.height(12.dp))
        LinearProgressIndicator(
            progress = { progress },
            modifier = Modifier
                .fillMaxWidth()
                .height(8.dp)
                .clip(RoundedCornerShape(4.dp)),
            color = SurviveBorder,
            trackColor = Color.White,
        )
        Spacer(Modifier.height(6.dp))
        Text(
            if (isMaxLevel) {
                "${me.points} pts · Max level reached"
            } else {
                val needed = (me.nextLevelPoints ?: me.points) - me.points
                "${me.points} / ${me.nextLevelPoints} pts · $needed to next level"
            },
            fontSize = 12.sp,
            color = SurviveText,
        )
    }
}

@Composable
private fun StatsGrid(me: MeResponse) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            StatTile(
                modifier = Modifier.weight(1f),
                icon = Icons.Default.Star,
                label = "Points",
                value = me.points.toString(),
            )
            StatTile(
                modifier = Modifier.weight(1f),
                icon = Icons.Default.Restaurant,
                label = "Submissions",
                value = me.submissionCount.toString(),
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            StatTile(
                modifier = Modifier.weight(1f),
                icon = Icons.Default.Verified,
                label = "Confirmations",
                value = me.confirmationCount.toString(),
            )
            StatTile(
                modifier = Modifier.weight(1f),
                icon = Icons.Default.LocalFireDepartment,
                label = "Day streak",
                value = me.dailyStreak.toString(),
            )
        }
    }
}

@Composable
private fun StatTile(
    modifier: Modifier = Modifier,
    icon: ImageVector,
    label: String,
    value: String,
) {
    Column(
        modifier
            .clip(RoundedCornerShape(14.dp))
            .border(0.5.dp, Color(0xFFE0E0E0), RoundedCornerShape(14.dp))
            .background(MaterialTheme.colorScheme.surface)
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Icon(
            icon,
            contentDescription = null,
            tint = SurviveBorder,
            modifier = Modifier.size(20.dp),
        )
        Spacer(Modifier.height(2.dp))
        Text(value, fontSize = 22.sp, fontWeight = FontWeight.Bold)
        Text(
            label,
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun DailyBonusBanner(streak: Int) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(Color(0xFFFFF4E2))
            .border(0.5.dp, Color(0xFFE8CC8A), RoundedCornerShape(14.dp))
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            Icons.Default.LocalFireDepartment,
            contentDescription = null,
            tint = Color(0xFFBA7517),
            modifier = Modifier.size(24.dp),
        )
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(
                if (streak > 0) "$streak-day streak!" else "Start your streak",
                fontSize = 14.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                "+1 point daily — come back tomorrow to keep it going.",
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun PerksCard(level: Int, canRate: Boolean, levelWeight: Int) {
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .border(0.5.dp, Color(0xFFE0E0E0), RoundedCornerShape(14.dp))
            .background(MaterialTheme.colorScheme.surface)
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(
                Icons.Default.EmojiEvents,
                contentDescription = null,
                tint = SurviveBorder,
                modifier = Modifier.size(20.dp),
            )
            Spacer(Modifier.width(8.dp))
            Text("Perks", fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
        }
        PerkRow(
            unlocked = true,
            title = "Submit menu items",
            subtitle = "Earn points for every new item",
        )
        PerkRow(
            unlocked = true,
            title = "Confirm prices (×$levelWeight weight)",
            subtitle = "Your votes count as $levelWeight at level $level",
        )
        PerkRow(
            unlocked = canRate,
            title = "Rate restaurants",
            subtitle = if (canRate) "Unlocked at level 3" else "Unlocks at level 3",
        )
    }
}

@Composable
private fun PerkRow(unlocked: Boolean, title: String, subtitle: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(
            if (unlocked) Icons.Default.CheckCircle else Icons.Default.Lock,
            contentDescription = null,
            tint = if (unlocked) SurviveBorder else MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(20.dp),
        )
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Text(
                title,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
                color = if (unlocked) MaterialTheme.colorScheme.onSurface
                else MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                subtitle,
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
