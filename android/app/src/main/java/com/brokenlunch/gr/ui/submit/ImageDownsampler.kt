package com.brokenlunch.gr.ui.submit

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import kotlin.math.max

private const val MAX_DIMENSION = 1920
private const val JPEG_QUALITY = 85

data class DownsampleResult(
    val bytes: ByteArray,
    val width: Int,
    val height: Int,
)

/**
 * Decode JPEG bytes, respect EXIF orientation, downsample so the longest edge
 * is <= 1920, and re-encode as JPEG quality 85. Saves Gemini vision cost and
 * upload time vs. a raw 3-5MB phone photo.
 */
fun downsampleJpeg(input: ByteArray): DownsampleResult {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(input, 0, input.size, bounds)
    val srcW = bounds.outWidth.takeIf { it > 0 } ?: return DownsampleResult(input, 0, 0)
    val srcH = bounds.outHeight.takeIf { it > 0 } ?: return DownsampleResult(input, 0, 0)

    val longest = max(srcW, srcH)
    var inSampleSize = 1
    while (longest / inSampleSize > MAX_DIMENSION * 2) {
        inSampleSize *= 2
    }

    val decodeOpts = BitmapFactory.Options().apply {
        this.inSampleSize = inSampleSize
        inPreferredConfig = Bitmap.Config.ARGB_8888
    }
    var bitmap = BitmapFactory.decodeByteArray(input, 0, input.size, decodeOpts)
        ?: return DownsampleResult(input, srcW, srcH)

    val rotation = readExifRotation(input)
    if (rotation != 0f) {
        val matrix = Matrix().apply { postRotate(rotation) }
        val rotated = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
        if (rotated !== bitmap) bitmap.recycle()
        bitmap = rotated
    }

    val currentLongest = max(bitmap.width, bitmap.height)
    if (currentLongest > MAX_DIMENSION) {
        val scale = MAX_DIMENSION.toFloat() / currentLongest
        val targetW = (bitmap.width * scale).toInt()
        val targetH = (bitmap.height * scale).toInt()
        val scaled = Bitmap.createScaledBitmap(bitmap, targetW, targetH, true)
        if (scaled !== bitmap) bitmap.recycle()
        bitmap = scaled
    }

    val out = ByteArrayOutputStream()
    bitmap.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out)
    val result = DownsampleResult(out.toByteArray(), bitmap.width, bitmap.height)
    bitmap.recycle()
    return result
}

private fun readExifRotation(bytes: ByteArray): Float = try {
    val exif = ExifInterface(ByteArrayInputStream(bytes))
    when (exif.getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)) {
        ExifInterface.ORIENTATION_ROTATE_90 -> 90f
        ExifInterface.ORIENTATION_ROTATE_180 -> 180f
        ExifInterface.ORIENTATION_ROTATE_270 -> 270f
        else -> 0f
    }
} catch (_: Throwable) {
    0f
}
