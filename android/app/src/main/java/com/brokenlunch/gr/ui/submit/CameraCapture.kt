package com.brokenlunch.gr.ui.submit

import android.content.Context
import android.util.Log
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.FlipCameraAndroid
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import java.util.concurrent.Executors

@Composable
fun CameraCapture(
    onCaptured: (ByteArray) -> Unit,
    onCancel: () -> Unit,
) {
    val ctx = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current

    var lensFacing by remember { mutableStateOf(CameraSelector.LENS_FACING_BACK) }
    val previewView = remember { PreviewView(ctx).apply { implementationMode = PreviewView.ImplementationMode.COMPATIBLE } }
    val imageCapture = remember {
        ImageCapture.Builder()
            .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
            .build()
    }
    val cameraExecutor = remember { Executors.newSingleThreadExecutor() }
    var capturing by remember { mutableStateOf(false) }
    var bindError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(lensFacing) {
        try {
            val provider = awaitCameraProvider(ctx)
            provider.unbindAll()
            val preview = Preview.Builder().build().apply {
                setSurfaceProvider(previewView.surfaceProvider)
            }
            val selector = CameraSelector.Builder().requireLensFacing(lensFacing).build()
            provider.bindToLifecycle(lifecycleOwner, selector, preview, imageCapture)
            bindError = null
        } catch (t: Throwable) {
            Log.e("CameraCapture", "Camera bind failed", t)
            bindError = "Camera init failed"
        }
    }

    DisposableEffect(Unit) {
        onDispose {
            cameraExecutor.shutdown()
            // Unbind on dispose so backgrounding releases the camera.
            ProcessCameraProvider.getInstance(ctx).also { future ->
                future.addListener({
                    runCatching { future.get().unbindAll() }
                }, ContextCompat.getMainExecutor(ctx))
            }
        }
    }

    Box(Modifier.fillMaxSize().background(Color.Black)) {
        if (bindError != null) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                androidx.compose.material3.Text(bindError!!, color = Color.White)
            }
        } else {
            AndroidView(
                factory = { previewView },
                modifier = Modifier.fillMaxSize(),
            )
        }

        IconButton(
            onClick = onCancel,
            modifier = Modifier
                .align(Alignment.TopStart)
                .padding(12.dp)
                .size(40.dp)
                .clip(CircleShape)
                .background(Color(0x88000000)),
        ) {
            Icon(Icons.Default.Close, contentDescription = "Close camera", tint = Color.White)
        }

        IconButton(
            onClick = {
                lensFacing = if (lensFacing == CameraSelector.LENS_FACING_BACK)
                    CameraSelector.LENS_FACING_FRONT
                else CameraSelector.LENS_FACING_BACK
            },
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(12.dp)
                .size(40.dp)
                .clip(CircleShape)
                .background(Color(0x88000000)),
        ) {
            Icon(Icons.Default.FlipCameraAndroid, contentDescription = "Flip camera", tint = Color.White)
        }

        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 40.dp),
        ) {
            Spacer(Modifier.width(0.dp))
            CaptureButton(
                capturing = capturing,
                onClick = {
                    if (capturing) return@CaptureButton
                    capturing = true
                    imageCapture.takePicture(
                        cameraExecutor,
                        object : ImageCapture.OnImageCapturedCallback() {
                            override fun onCaptureSuccess(image: ImageProxy) {
                                val bytes = image.toJpegBytes()
                                image.close()
                                capturing = false
                                onCaptured(bytes)
                            }

                            override fun onError(exception: ImageCaptureException) {
                                Log.e("CameraCapture", "Capture failed", exception)
                                capturing = false
                            }
                        },
                    )
                },
            )
        }
    }
}

@Composable
private fun CaptureButton(capturing: Boolean, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .size(72.dp)
            .clip(CircleShape)
            .background(Color.White)
            .padding(6.dp),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .clip(CircleShape)
                .background(if (capturing) Color.Gray else Color(0xFFEFEFEF)),
        )
        Box(
            modifier = Modifier
                .size(56.dp)
                .clip(CircleShape)
                .background(Color(0xFFEFEFEF)),
            contentAlignment = Alignment.Center,
        ) {
            if (capturing) {
                CircularProgressIndicator(
                    strokeWidth = 3.dp,
                    modifier = Modifier.size(28.dp),
                )
            } else {
                IconButton(onClick = onClick, modifier = Modifier.fillMaxSize()) {
                    Box(
                        modifier = Modifier
                            .size(48.dp)
                            .clip(CircleShape)
                            .background(Color.White),
                    )
                }
            }
        }
    }
}

private suspend fun awaitCameraProvider(ctx: Context): ProcessCameraProvider =
    kotlinx.coroutines.suspendCancellableCoroutine { cont ->
        val future = ProcessCameraProvider.getInstance(ctx)
        future.addListener({
            try {
                cont.resumeWith(Result.success(future.get()))
            } catch (t: Throwable) {
                cont.resumeWith(Result.failure(t))
            }
        }, ContextCompat.getMainExecutor(ctx))
    }

private fun ImageProxy.toJpegBytes(): ByteArray {
    val buffer = planes[0].buffer
    val bytes = ByteArray(buffer.remaining())
    buffer.get(bytes)
    return bytes
}
