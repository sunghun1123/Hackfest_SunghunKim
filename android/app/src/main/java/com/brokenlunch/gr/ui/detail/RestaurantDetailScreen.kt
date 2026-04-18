package com.brokenlunch.gr.ui.detail

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Flag
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material.icons.filled.Public
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.brokenlunch.gr.data.model.MenuItem
import com.brokenlunch.gr.data.model.ReportReason
import com.brokenlunch.gr.data.model.RestaurantDetail
import com.brokenlunch.gr.data.model.Tier
import com.brokenlunch.gr.data.model.VerificationStatus
import com.brokenlunch.gr.ui.common.VerificationBadge
import com.brokenlunch.gr.ui.common.formatPriceCents
import com.brokenlunch.gr.ui.theme.AiParsedBg
import com.brokenlunch.gr.ui.theme.AiParsedText
import com.brokenlunch.gr.ui.theme.CostBorder
import com.brokenlunch.gr.ui.theme.CostText
import com.brokenlunch.gr.ui.theme.LuxuryBorder
import com.brokenlunch.gr.ui.theme.LuxuryText
import com.brokenlunch.gr.ui.theme.SurviveBorder
import com.brokenlunch.gr.ui.theme.SurviveText

private fun tierBorder(tier: Tier): Color = when (tier) {
    Tier.SURVIVE -> SurviveBorder
    Tier.COST_EFFECTIVE -> CostBorder
    Tier.LUXURY -> LuxuryBorder
}

private fun tierText(tier: Tier): Color = when (tier) {
    Tier.SURVIVE -> SurviveText
    Tier.COST_EFFECTIVE -> CostText
    Tier.LUXURY -> LuxuryText
}

private fun tierLabel(tier: Tier): String = when (tier) {
    Tier.SURVIVE -> "Survive · $0-5"
    Tier.COST_EFFECTIVE -> "Cost-effective · $5-10"
    Tier.LUXURY -> "Luxury · $10-15"
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RestaurantDetailScreen(
    onBack: () -> Unit = {},
    onSubmitClick: (restaurantId: String) -> Unit = {},
    vm: DetailViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsStateWithLifecycle()
    val ctx = LocalContext.current
    val snackbar = remember { SnackbarHostState() }

    var reportTarget by remember { mutableStateOf<MenuItem?>(null) }
    var differentPriceTarget by remember { mutableStateOf<MenuItem?>(null) }
    var rateDialogOpen by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        vm.events.collect { ev ->
            when (ev) {
                is DetailEvent.Toast -> snackbar.showSnackbar(ev.message)
            }
        }
    }
    LaunchedEffect(state.error) { state.error?.let { snackbar.showSnackbar(it) } }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(state.restaurant?.name ?: "Restaurant", fontSize = 16.sp) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { inner ->
        Box(Modifier.fillMaxSize().padding(inner)) {
            when {
                state.loading && state.restaurant == null -> Box(
                    Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center,
                ) { CircularProgressIndicator() }

                state.restaurant == null -> Box(
                    Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center,
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(state.error ?: "Couldn't load restaurant")
                        Spacer(Modifier.height(8.dp))
                        TextButton(onClick = vm::loadDetail) { Text("Retry") }
                    }
                }

                else -> {
                    val r = state.restaurant!!
                    val tiered = vm.tieredMenu(r)
                    val isEmpty = r.menu.isEmpty()
                    val canRate = state.me?.canRateRestaurants == true
                    DetailContent(
                        restaurant = r,
                        isEmpty = isEmpty,
                        tiered = tiered,
                        confirmingIds = state.confirmingIds,
                        canRate = canRate,
                        onPhoneClick = { phone ->
                            ctx.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:$phone")))
                        },
                        onWebsiteClick = { url ->
                            ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                        },
                        onConfirm = vm::confirmPrice,
                        onReportFlagClick = { item -> reportTarget = item },
                        onDifferentPriceClick = { item -> differentPriceTarget = item },
                        onRateClick = { rateDialogOpen = true },
                        onAddMenuClick = { onSubmitClick(r.id) },
                        onTakeMenuPhotoClick = { onSubmitClick(r.id) },
                    )
                }
            }
        }
    }

    reportTarget?.let { target ->
        ReportBottomSheet(
            menuItemName = target.name,
            onDismiss = { reportTarget = null },
            onSubmit = { reason: ReportReason, comment ->
                vm.reportMenu(target.id, reason, comment)
                reportTarget = null
            },
        )
    }

    differentPriceTarget?.let { target ->
        DifferentPriceDialog(
            menuItemName = target.name,
            currentPriceCents = target.priceCents,
            onDismiss = { differentPriceTarget = null },
            onSubmit = { newPriceCents ->
                vm.reportDifferentPrice(target.id, newPriceCents)
                differentPriceTarget = null
            },
        )
    }

    if (rateDialogOpen) {
        val name = state.restaurant?.name ?: "restaurant"
        RateRestaurantDialog(
            restaurantName = name,
            onDismiss = { rateDialogOpen = false },
            onSubmit = { score, comment ->
                vm.rateRestaurant(score, comment)
                rateDialogOpen = false
            },
        )
    }
}

@Composable
private fun DetailContent(
    restaurant: RestaurantDetail,
    isEmpty: Boolean,
    tiered: List<Pair<Tier, List<MenuItem>>>,
    confirmingIds: Set<String>,
    canRate: Boolean,
    onPhoneClick: (String) -> Unit,
    onWebsiteClick: (String) -> Unit,
    onConfirm: (String) -> Unit,
    onReportFlagClick: (MenuItem) -> Unit,
    onDifferentPriceClick: (MenuItem) -> Unit,
    onRateClick: () -> Unit,
    onAddMenuClick: () -> Unit,
    onTakeMenuPhotoClick: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(bottom = 24.dp),
    ) {
        Header(
            restaurant = restaurant,
            onPhoneClick = onPhoneClick,
            onWebsiteClick = onWebsiteClick,
        )

        if (isEmpty) {
            EmptyMenuCta(onTakeMenuPhotoClick = onTakeMenuPhotoClick)
        } else {
            tiered.forEach { (tier, items) ->
                TierSection(
                    tier = tier,
                    items = items,
                    confirmingIds = confirmingIds,
                    onConfirm = onConfirm,
                    onReportFlagClick = onReportFlagClick,
                    onDifferentPriceClick = onDifferentPriceClick,
                )
            }
        }

        Spacer(Modifier.height(16.dp))

        Column(Modifier.padding(horizontal = 16.dp)) {
            OutlinedButton(
                onClick = onAddMenuClick,
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Add more menu items") }

            if (canRate) {
                Spacer(Modifier.height(8.dp))
                OutlinedButton(
                    onClick = onRateClick,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Icon(Icons.Default.Star, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Rate this restaurant")
                }
            }
        }
    }
}

@Composable
private fun Header(
    restaurant: RestaurantDetail,
    onPhoneClick: (String) -> Unit,
    onWebsiteClick: (String) -> Unit,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 16.dp),
    ) {
        Text(
            restaurant.name,
            fontSize = 22.sp,
            fontWeight = FontWeight.Medium,
        )
        Spacer(Modifier.height(6.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            restaurant.googleRating?.let {
                Icon(
                    Icons.Default.Star,
                    contentDescription = "Google rating",
                    tint = Color(0xFFF5B400),
                    modifier = Modifier.size(14.dp),
                )
                Spacer(Modifier.width(2.dp))
                Text("%.1f".format(it), fontSize = 12.sp)
                Spacer(Modifier.width(10.dp))
            }
            restaurant.appRating?.let {
                Text("App %.1f".format(it), fontSize = 12.sp)
                Spacer(Modifier.width(4.dp))
                Text("(${restaurant.ratingCount})", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }

        restaurant.address?.let { addr ->
            Spacer(Modifier.height(8.dp))
            Text(addr, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }

        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            restaurant.phone?.let { phone ->
                OutlinedButton(onClick = { onPhoneClick(phone) }, contentPadding = ButtonDefaults.ContentPadding) {
                    Icon(Icons.Default.Phone, contentDescription = null, modifier = Modifier.size(14.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("Call", fontSize = 12.sp)
                }
            }
            restaurant.website?.let { site ->
                OutlinedButton(onClick = { onWebsiteClick(site) }) {
                    Icon(Icons.Default.Public, contentDescription = null, modifier = Modifier.size(14.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("Website", fontSize = 12.sp)
                }
            }
        }
    }
    HorizontalDivider(color = Color(0x11000000))
}

@Composable
private fun EmptyMenuCta(onTakeMenuPhotoClick: () -> Unit) {
    Column(
        Modifier
            .padding(16.dp)
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(AiParsedBg)
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("\uD83D\uDCCB", fontSize = 40.sp)
        Spacer(Modifier.height(12.dp))
        Text(
            "No menu registered yet",
            fontSize = 16.sp,
            fontWeight = FontWeight.Medium,
            color = AiParsedText,
        )
        Spacer(Modifier.height(6.dp))
        Text(
            "Be the first to add a menu\nand earn +15 points!",
            fontSize = 13.sp,
            color = AiParsedText,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
        )
        Spacer(Modifier.height(16.dp))
        Button(onClick = onTakeMenuPhotoClick) {
            Icon(Icons.Default.CameraAlt, contentDescription = null, modifier = Modifier.size(16.dp))
            Spacer(Modifier.width(6.dp))
            Text("Take menu photo")
        }
    }
}

@Composable
private fun TierSection(
    tier: Tier,
    items: List<MenuItem>,
    confirmingIds: Set<String>,
    onConfirm: (String) -> Unit,
    onReportFlagClick: (MenuItem) -> Unit,
    onDifferentPriceClick: (MenuItem) -> Unit,
) {
    val borderColor = tierBorder(tier)
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .drawBehind {
                drawRect(
                    color = borderColor,
                    topLeft = Offset(0f, 0f),
                    size = Size(3.dp.toPx(), size.height),
                )
            }
            .padding(start = 14.dp, end = 16.dp, top = 10.dp, bottom = 8.dp),
    ) {
        Text(
            tierLabel(tier),
            fontSize = 13.sp,
            fontWeight = FontWeight.Medium,
            color = tierText(tier),
        )
        Spacer(Modifier.weight(1f))
        Text("${items.size}", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    Column(Modifier.padding(horizontal = 16.dp)) {
        items.forEach { item ->
            MenuCard(
                item = item,
                tierColor = tierText(tier),
                confirming = item.id in confirmingIds,
                onConfirm = { onConfirm(item.id) },
                onReportFlag = { onReportFlagClick(item) },
                onDifferentPrice = { onDifferentPriceClick(item) },
            )
            Spacer(Modifier.height(10.dp))
        }
    }
}

@Composable
private fun MenuCard(
    item: MenuItem,
    tierColor: Color,
    confirming: Boolean,
    onConfirm: () -> Unit,
    onReportFlag: () -> Unit,
    onDifferentPrice: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .border(0.5.dp, Color(0xFFE0E0E0), RoundedCornerShape(12.dp))
            .background(MaterialTheme.colorScheme.surface)
            .padding(horizontal = 16.dp, vertical = 14.dp),
    ) {
        Row(verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f)) {
                Text(item.name, fontSize = 16.sp, fontWeight = FontWeight.Medium)
                item.description?.takeIf { it.isNotBlank() }?.let { desc ->
                    Spacer(Modifier.height(2.dp))
                    Text(desc, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            Spacer(Modifier.width(8.dp))
            Text(
                formatPriceCents(item.priceCents),
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium,
                color = tierColor,
            )
            IconButton(
                onClick = onReportFlag,
                modifier = Modifier.size(28.dp),
            ) {
                Icon(
                    Icons.Default.Flag,
                    contentDescription = "Report this price",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(16.dp),
                )
            }
        }

        Spacer(Modifier.height(8.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            VerificationBadge(item.verificationStatus)
            Spacer(Modifier.width(8.dp))
            Text(
                text = metaLine(item),
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        Spacer(Modifier.height(10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = onConfirm,
                enabled = !confirming,
                modifier = Modifier.weight(1f),
            ) { Text(if (confirming) "..." else "\u2713 Confirm price", fontSize = 12.sp) }
            OutlinedButton(
                onClick = onDifferentPrice,
                enabled = !confirming,
                modifier = Modifier.weight(1f),
            ) { Text("\u2717 Different price", fontSize = 12.sp) }
        }
    }
}

private fun metaLine(item: MenuItem): String {
    return when (item.verificationStatus) {
        VerificationStatus.NEEDS_VERIFICATION -> "needs verification"
        else -> {
            val usersLabel = if (item.confirmationCount == 1) "1 user" else "${item.confirmationCount} users"
            val when_ = item.lastVerifiedAt?.substringBefore('T') ?: "—"
            "$usersLabel · $when_"
        }
    }
}
