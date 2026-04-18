package com.brokenlunch.gr.ui.submit

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SubmitScreen(
    onExit: () -> Unit = {},
    vm: SubmitViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsStateWithLifecycle()
    val ctx = LocalContext.current
    val snackbar = remember { SnackbarHostState() }

    var cameraPermissionAsked by remember { mutableStateOf(false) }
    var cameraPermissionDenied by remember { mutableStateOf(false) }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
    ) { granted ->
        cameraPermissionAsked = true
        cameraPermissionDenied = !granted
    }

    LaunchedEffect(state.stage) {
        if (state.stage == SubmitStage.CAMERA_OPEN && !cameraPermissionAsked) {
            val granted = ContextCompat.checkSelfPermission(
                ctx, Manifest.permission.CAMERA,
            ) == PackageManager.PERMISSION_GRANTED
            if (granted) {
                cameraPermissionAsked = true
            } else {
                permissionLauncher.launch(Manifest.permission.CAMERA)
            }
        }
    }

    LaunchedEffect(state.error) {
        state.error?.let {
            snackbar.showSnackbar(it)
            vm.clearError()
        }
    }

    // Auto-exit after DONE → user taps Done button; no auto-timeout (keep celebratory screen up).

    Scaffold(
        topBar = {
            if (state.stage != SubmitStage.CAMERA_OPEN) {
                TopAppBar(
                    title = {
                        Text(
                            when (state.stage) {
                                SubmitStage.SELECTING_RESTAURANT -> "Add menu item"
                                SubmitStage.PARSING -> "Reading menu…"
                                SubmitStage.EDITING -> "Review items"
                                SubmitStage.SUBMITTING -> "Submitting…"
                                SubmitStage.DONE -> "Done"
                                SubmitStage.CAMERA_OPEN -> ""
                            },
                            fontWeight = FontWeight.Medium,
                        )
                    },
                    navigationIcon = {
                        IconButton(onClick = onExit) {
                            Icon(
                                Icons.AutoMirrored.Filled.ArrowBack,
                                contentDescription = "Back",
                            )
                        }
                    },
                )
            }
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { inner ->
        Box(Modifier.fillMaxSize().padding(inner)) {
            when (state.stage) {
                SubmitStage.SELECTING_RESTAURANT -> RestaurantPicker(
                    query = state.searchQuery,
                    restaurants = state.nearbyRestaurants,
                    onQueryChange = vm::setSearchQuery,
                    onSelect = vm::selectRestaurant,
                )

                SubmitStage.CAMERA_OPEN -> {
                    if (cameraPermissionDenied) {
                        CameraPermissionDenied(
                            onRetry = {
                                cameraPermissionDenied = false
                                permissionLauncher.launch(Manifest.permission.CAMERA)
                            },
                            onCancel = onExit,
                        )
                    } else if (cameraPermissionAsked) {
                        CameraCapture(
                            onCaptured = vm::onPhotoCaptured,
                            onCancel = {
                                if (state.restaurantId == null) onExit() else vm.cancelCamera()
                            },
                        )
                    } else {
                        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator()
                        }
                    }
                }

                SubmitStage.PARSING -> ParsingView()

                SubmitStage.EDITING -> EditingScreen(
                    restaurantName = state.restaurantName,
                    items = state.items,
                    parseWarnings = state.parseWarnings,
                    onNameChange = vm::updateItemName,
                    onPriceChange = vm::updateItemPrice,
                    onDelete = vm::deleteItem,
                    onAddManual = vm::addManualItem,
                    onRetake = vm::retakePhoto,
                    onSubmitAll = vm::submitAll,
                )

                SubmitStage.SUBMITTING -> Box(
                    Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center,
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        CircularProgressIndicator()
                        Spacer(Modifier.height(12.dp))
                        Text("Submitting items…", fontSize = 13.sp)
                    }
                }

                SubmitStage.DONE -> DoneScreen(
                    result = state.result,
                    onDoneBack = onExit,
                    onSubmitMore = vm::retakePhoto,
                )
            }
        }
    }
}

@Composable
private fun ParsingView() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            CircularProgressIndicator()
            Spacer(Modifier.height(16.dp))
            Text("Reading menu with Gemini…", fontSize = 14.sp, fontWeight = FontWeight.Medium)
            Spacer(Modifier.height(4.dp))
            Text(
                "This usually takes a few seconds.",
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun CameraPermissionDenied(onRetry: () -> Unit, onCancel: () -> Unit) {
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text("Camera needed") },
        text = {
            Text("We need camera access to photograph the menu. You can grant it in settings or try again.")
        },
        confirmButton = { TextButton(onClick = onRetry) { Text("Try again") } },
        dismissButton = { TextButton(onClick = onCancel) { Text("Cancel") } },
    )
}
