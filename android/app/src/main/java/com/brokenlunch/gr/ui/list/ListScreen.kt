package com.brokenlunch.gr.ui.list

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.brokenlunch.gr.data.model.RestaurantNearby
import com.brokenlunch.gr.data.model.Tier
import com.brokenlunch.gr.ui.common.VerificationBadge
import com.brokenlunch.gr.ui.common.formatDistanceMeters
import com.brokenlunch.gr.ui.common.formatPriceCents
import com.brokenlunch.gr.ui.map.categoryEmoji
import com.brokenlunch.gr.ui.theme.AiParsedBg
import com.brokenlunch.gr.ui.theme.AiParsedText
import com.brokenlunch.gr.ui.theme.CostBg
import com.brokenlunch.gr.ui.theme.CostBorder
import com.brokenlunch.gr.ui.theme.CostText
import com.brokenlunch.gr.ui.theme.EmptyBg
import com.brokenlunch.gr.ui.theme.EmptyIcon
import com.brokenlunch.gr.ui.theme.LuxuryBg
import com.brokenlunch.gr.ui.theme.LuxuryBorder
import com.brokenlunch.gr.ui.theme.LuxuryText
import com.brokenlunch.gr.ui.theme.SurviveBg
import com.brokenlunch.gr.ui.theme.SurviveBorder
import com.brokenlunch.gr.ui.theme.SurviveText

private fun tierBorder(tier: Tier?): Color = when (tier) {
    Tier.SURVIVE -> SurviveBorder
    Tier.COST_EFFECTIVE -> CostBorder
    Tier.LUXURY -> LuxuryBorder
    null -> Color(0xFFB4B2A9)  // help us — gray
}

private fun tierBg(tier: Tier?): Color = when (tier) {
    Tier.SURVIVE -> SurviveBg
    Tier.COST_EFFECTIVE -> CostBg
    Tier.LUXURY -> LuxuryBg
    null -> EmptyBg
}

private fun tierText(tier: Tier?): Color = when (tier) {
    Tier.SURVIVE -> SurviveText
    Tier.COST_EFFECTIVE -> CostText
    Tier.LUXURY -> LuxuryText
    null -> Color(0xFF5F5E5A)
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalFoundationApi::class)
@Composable
fun ListScreen(
    onRestaurantClick: (String) -> Unit = {},
    vm: ListViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }

    LaunchedEffect(Unit) { vm.initIfNeeded() }
    LaunchedEffect(state.error) { state.error?.let { snackbar.showSnackbar(it) } }

    Scaffold(
        topBar = {
            TopAppBar(title = { Text("Nearby", fontWeight = FontWeight.Medium) })
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { inner ->
        Column(Modifier.fillMaxSize().padding(inner)) {
            FilterBar(
                sort = state.sortMode,
                showEmpty = state.showEmpty,
                onSortChange = vm::setSort,
                onShowEmptyChange = vm::setShowEmpty,
            )
            HorizontalDivider()

            if (state.loading && state.sections.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            } else if (state.sections.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(
                        "No restaurants nearby.",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            } else {
                LazyColumn(Modifier.fillMaxSize()) {
                    state.sections.forEach { section ->
                        stickyHeader(key = "h-${section.id}") {
                            SectionHeader(
                                title = section.title,
                                subtitle = section.subtitle,
                                count = section.restaurants.size,
                                tier = section.tier,
                            )
                        }
                        items(section.restaurants, key = { "${section.id}-${it.id}" }) { r ->
                            if (section.tier == null) {
                                EmptyRestaurantRow(r, onClick = { onRestaurantClick(r.id) })
                            } else {
                                MenuItemRow(r, section.tier, onClick = { onRestaurantClick(r.id) })
                            }
                            HorizontalDivider(color = Color(0x11000000))
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FilterBar(
    sort: SortMode,
    showEmpty: Boolean,
    onSortChange: (SortMode) -> Unit,
    onShowEmptyChange: (Boolean) -> Unit,
) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        FilterChip(
            selected = sort == SortMode.DISTANCE,
            onClick = { onSortChange(SortMode.DISTANCE) },
            label = { Text("Distance", fontSize = 11.sp, fontWeight = FontWeight.Medium) },
            colors = FilterChipDefaults.filterChipColors(),
        )
        FilterChip(
            selected = sort == SortMode.PRICE,
            onClick = { onSortChange(SortMode.PRICE) },
            label = { Text("Price", fontSize = 11.sp, fontWeight = FontWeight.Medium) },
            colors = FilterChipDefaults.filterChipColors(),
        )
        Spacer(Modifier.weight(1f))
        Text("Include empty", fontSize = 12.sp, modifier = Modifier.padding(end = 6.dp))
        Switch(
            checked = showEmpty,
            onCheckedChange = onShowEmptyChange,
        )
    }
}

@Composable
private fun SectionHeader(
    title: String,
    subtitle: String,
    count: Int,
    tier: Tier?,
) {
    val borderColor = tierBorder(tier)
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface)
            .drawBehind {
                drawRect(
                    color = borderColor,
                    topLeft = Offset(0f, 0f),
                    size = androidx.compose.ui.geometry.Size(3.dp.toPx(), size.height),
                )
            }
            .padding(start = 14.dp, end = 16.dp, top = 10.dp, bottom = 10.dp),
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                text = title,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
                color = tierText(tier),
            )
            Text(
                text = subtitle,
                fontSize = 10.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Text(
            text = "$count spots",
            fontSize = 10.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun MenuItemRow(
    r: RestaurantNearby,
    tier: Tier,
    onClick: () -> Unit,
) {
    val menu = r.cheapestMenu ?: return
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp),
    ) {
        Box(
            modifier = Modifier
                .size(32.dp)
                .clip(CircleShape)
                .background(tierBg(tier), CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Text(categoryEmoji(r.category), fontSize = 14.sp)
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(r.name, fontSize = 13.sp, fontWeight = FontWeight.Medium)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = "${menu.name} · ${formatDistanceMeters(r.distanceM)}",
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f, fill = false),
                )
                Spacer(Modifier.width(6.dp))
                VerificationBadge(menu.verificationStatus)
            }
        }
        Spacer(Modifier.width(8.dp))
        Text(
            text = formatPriceCents(menu.priceCents),
            fontSize = 13.sp,
            fontWeight = FontWeight.Medium,
            color = tierText(tier),
        )
    }
}

@Composable
private fun EmptyRestaurantRow(
    r: RestaurantNearby,
    onClick: () -> Unit,
) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp),
    ) {
        Box(
            modifier = Modifier
                .size(32.dp)
                .clip(CircleShape)
                .background(EmptyBg, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Text("?", fontSize = 14.sp, fontWeight = FontWeight.Medium, color = EmptyIcon)
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(r.name, fontSize = 13.sp, fontWeight = FontWeight.Medium)
            Text(
                text = "${r.category ?: "restaurant"} · ${formatDistanceMeters(r.distanceM)}",
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Box(
            modifier = Modifier
                .clip(RoundedCornerShape(999.dp))
                .background(AiParsedBg)
                .padding(horizontal = 8.dp, vertical = 3.dp),
        ) {
            Text(
                "+15 pts",
                fontSize = 10.sp,
                fontWeight = FontWeight.Medium,
                color = AiParsedText,
            )
        }
    }
}
