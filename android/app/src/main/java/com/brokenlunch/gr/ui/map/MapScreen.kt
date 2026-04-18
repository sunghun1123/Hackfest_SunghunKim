package com.brokenlunch.gr.ui.map

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.FloatingActionButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.brokenlunch.gr.data.model.MenuStatus
import com.brokenlunch.gr.data.model.RestaurantNearby
import com.brokenlunch.gr.data.model.Tier
import com.brokenlunch.gr.ui.theme.CostBg
import com.brokenlunch.gr.ui.theme.CostBorder
import com.brokenlunch.gr.ui.theme.CostText
import com.brokenlunch.gr.ui.theme.LuxuryBg
import com.brokenlunch.gr.ui.theme.LuxuryBorder
import com.brokenlunch.gr.ui.theme.LuxuryText
import com.brokenlunch.gr.ui.theme.SurviveBg
import com.brokenlunch.gr.ui.theme.SurviveBorder
import com.brokenlunch.gr.ui.theme.SurviveText
import com.google.android.gms.maps.CameraUpdateFactory
import com.google.android.gms.maps.model.CameraPosition
import com.google.android.gms.maps.model.LatLng
import com.google.maps.android.clustering.ClusterItem
import com.google.maps.android.compose.CameraPositionState
import com.google.maps.android.compose.GoogleMap
import com.google.maps.android.compose.MapProperties
import com.google.maps.android.compose.MapUiSettings
import com.google.maps.android.compose.MarkerComposable
import com.google.maps.android.compose.clustering.Clustering
import com.google.maps.android.compose.rememberCameraPositionState
import kotlinx.coroutines.launch

private class RestaurantClusterItem(val r: RestaurantNearby) : ClusterItem {
    private val pos = LatLng(r.lat, r.lng)
    override fun getPosition(): LatLng = pos
    override fun getTitle(): String? = r.name
    override fun getSnippet(): String? = null
    override fun getZIndex(): Float? = null
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MapScreen(
    onRestaurantClick: (String) -> Unit = {},
    vm: MapViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsStateWithLifecycle()
    val ctx = LocalContext.current
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    val cameraState = rememberCameraPositionState {
        position = CameraPosition.fromLatLngZoom(GR_CENTER, FALLBACK_ZOOM)
    }

    var searchOpen by remember { mutableStateOf(false) }
    var searchQuery by remember { mutableStateOf("") }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) vm.onLocationPermissionGranted() else vm.onLocationPermissionDenied()
    }

    LaunchedEffect(Unit) {
        val granted = ContextCompat.checkSelfPermission(
            ctx, Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        if (granted) {
            vm.onLocationPermissionGranted()
        } else {
            permissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
        }
    }

    LaunchedEffect(state.center) {
        cameraState.position = CameraPosition.fromLatLngZoom(
            state.center,
            if (state.userLocation == null) FALLBACK_ZOOM else DEFAULT_ZOOM,
        )
    }

    LaunchedEffect(state.error, state.locationPermissionDenied) {
        state.error?.let { snackbar.showSnackbar(it) }
        if (state.locationPermissionDenied) {
            snackbar.showSnackbar("Location denied — showing Grand Rapids")
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Broke People's Food Map", fontWeight = FontWeight.Medium) },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                ),
                actions = {
                    IconButton(onClick = { searchOpen = true }) {
                        Icon(Icons.Default.Search, contentDescription = "Search")
                    }
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.padding(end = 12.dp),
                    ) {
                        Text(
                            "Show empty",
                            fontSize = 12.sp,
                            modifier = Modifier.padding(end = 6.dp),
                        )
                        Switch(
                            checked = state.showEmpty,
                            onCheckedChange = { vm.toggleShowEmpty(it) },
                        )
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
        floatingActionButton = {
            FloatingActionButton(
                onClick = { vm.recenterToUser(cameraState) },
                containerColor = MaterialTheme.colorScheme.surface,
                contentColor = MaterialTheme.colorScheme.onSurface,
                elevation = FloatingActionButtonDefaults.elevation(defaultElevation = 4.dp),
                modifier = Modifier.size(40.dp),
            ) {
                Icon(Icons.Default.MyLocation, contentDescription = "My location")
            }
        },
    ) { inner ->
        Box(Modifier.fillMaxSize().padding(inner)) {
            MapContent(
                cameraState = cameraState,
                restaurants = vm.visibleRestaurants(),
                onClick = onRestaurantClick,
                padding = PaddingValues(top = 56.dp),  // leave room for FilterRow
            )

            FilterRow(
                selected = state.selectedTiers,
                onToggle = vm::toggleTier,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 8.dp),
            )

            if (state.loading) {
                Box(
                    Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator()
                }
            }
        }
    }

    if (searchOpen) {
        SearchSheet(
            query = searchQuery,
            restaurants = state.restaurants,
            onQueryChange = { searchQuery = it },
            onPick = { id ->
                searchOpen = false
                searchQuery = ""
                onRestaurantClick(id)
            },
            onDismiss = {
                searchOpen = false
                searchQuery = ""
            },
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SearchSheet(
    query: String,
    restaurants: List<RestaurantNearby>,
    onQueryChange: (String) -> Unit,
    onPick: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val trimmed = query.trim()
    val matches = remember(trimmed, restaurants) {
        if (trimmed.isEmpty()) {
            restaurants.sortedBy { it.distanceM }.take(20)
        } else {
            restaurants
                .filter { it.name.contains(trimmed, ignoreCase = true) }
                .sortedBy { it.distanceM }
                .take(50)
        }
    }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        OutlinedTextField(
            value = query,
            onValueChange = onQueryChange,
            placeholder = { Text("Search nearby restaurants…", fontSize = 13.sp) },
            leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            shape = RoundedCornerShape(24.dp),
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp),
        )
        HorizontalDivider()
        if (matches.isEmpty()) {
            Box(
                Modifier
                    .fillMaxWidth()
                    .padding(32.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    if (trimmed.isEmpty()) "Start typing to search."
                    else "No match for \"$trimmed\".",
                    fontSize = 13.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        } else {
            LazyColumn(Modifier.heightIn(max = 480.dp)) {
                items(matches, key = { it.id }) { r ->
                    SearchResultRow(r = r, onClick = { onPick(r.id) })
                    HorizontalDivider(color = Color(0x11000000))
                }
            }
        }
    }
}

@Composable
private fun SearchResultRow(r: RestaurantNearby, onClick: () -> Unit) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp),
    ) {
        Text(categoryEmoji(r.category), fontSize = 20.sp)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(r.name, fontSize = 14.sp, fontWeight = FontWeight.Medium)
            val subtitle = when {
                r.cheapestMenu != null -> "from $${"%.2f".format(r.cheapestMenu.priceCents / 100.0)} · ${r.distanceM} m"
                else -> "no menu yet · ${r.distanceM} m"
            }
            Text(
                subtitle,
                fontSize = 11.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun MapContent(
    cameraState: CameraPositionState,
    restaurants: List<RestaurantNearby>,
    onClick: (String) -> Unit,
    padding: PaddingValues,
) {
    val items = remember(restaurants) { restaurants.map { RestaurantClusterItem(it) } }
    val scope = rememberCoroutineScope()
    GoogleMap(
        cameraPositionState = cameraState,
        properties = MapProperties(isMyLocationEnabled = false),
        uiSettings = MapUiSettings(
            zoomControlsEnabled = false,
            myLocationButtonEnabled = false,
            mapToolbarEnabled = false,
        ),
        contentPadding = padding,
        modifier = Modifier.fillMaxSize(),
    ) {
        if (restaurants.size > 50) {
            Clustering(
                items = items,
                onClusterClick = { cluster ->
                    val newZoom = (cameraState.position.zoom + 2f).coerceAtMost(20f)
                    scope.launch {
                        cameraState.animate(
                            CameraUpdateFactory.newLatLngZoom(cluster.position, newZoom),
                            durationMs = 400,
                        )
                    }
                    true
                },
                onClusterItemClick = { item ->
                    onClick(item.r.id)
                    true
                },
                clusterItemContent = { item -> PinForRestaurant(item.r) },
            )
        } else {
            for (item in items) {
                val r = item.r
                MarkerComposable(
                    keys = arrayOf<Any>(r.id, r.menuStatus.name, r.cheapestMenu?.tier?.name ?: "none"),
                    state = com.google.maps.android.compose.rememberMarkerState(
                        position = item.position,
                    ),
                    onClick = {
                        onClick(r.id)
                        true
                    },
                ) {
                    PinForRestaurant(r)
                }
            }
        }
    }
}

@Composable
private fun PinForRestaurant(r: RestaurantNearby) {
    when (r.menuStatus) {
        MenuStatus.POPULATED_VERIFIED -> {
            val tier = r.cheapestMenu?.tier ?: Tier.SURVIVE
            val price = r.cheapestMenu?.priceCents ?: 0
            PopulatedVerifiedPin(tier, price, r.category)
        }
        MenuStatus.POPULATED_AI -> {
            val tier = r.cheapestMenu?.tier ?: Tier.SURVIVE
            val price = r.cheapestMenu?.priceCents ?: 0
            PopulatedAiPin(tier, price, r.category)
        }
        MenuStatus.EMPTY -> EmptyPin()
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FilterRow(
    selected: Set<Tier>,
    onToggle: (Tier) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        modifier = modifier,
    ) {
        TierChip(
            label = "Survive ≤$5",
            selected = Tier.SURVIVE in selected,
            bg = SurviveBg, border = SurviveBorder, text = SurviveText,
            onClick = { onToggle(Tier.SURVIVE) },
        )
        TierChip(
            label = "Cost-effective $5-10",
            selected = Tier.COST_EFFECTIVE in selected,
            bg = CostBg, border = CostBorder, text = CostText,
            onClick = { onToggle(Tier.COST_EFFECTIVE) },
        )
        TierChip(
            label = "Luxury $10-15",
            selected = Tier.LUXURY in selected,
            bg = LuxuryBg, border = LuxuryBorder, text = LuxuryText,
            onClick = { onToggle(Tier.LUXURY) },
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TierChip(
    label: String,
    selected: Boolean,
    bg: Color,
    border: Color,
    text: Color,
    onClick: () -> Unit,
) {
    FilterChip(
        selected = selected,
        onClick = onClick,
        label = {
            Text(
                label,
                fontSize = 11.sp,
                fontWeight = FontWeight.Medium,
                color = if (selected) text else MaterialTheme.colorScheme.onSurfaceVariant,
            )
        },
        colors = FilterChipDefaults.filterChipColors(
            selectedContainerColor = bg,
            containerColor = MaterialTheme.colorScheme.surface,
            selectedLabelColor = text,
        ),
        border = FilterChipDefaults.filterChipBorder(
            enabled = true,
            selected = selected,
            borderColor = Color(0xFFE0E0E0),
            selectedBorderColor = border,
            borderWidth = 1.dp,
            selectedBorderWidth = 1.5.dp,
        ),
    )
}
