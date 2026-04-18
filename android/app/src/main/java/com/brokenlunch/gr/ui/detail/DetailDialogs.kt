package com.brokenlunch.gr.ui.detail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.selectable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.StarBorder
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.Button
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.brokenlunch.gr.data.model.ReportReason

private val REASON_ORDER = listOf(
    ReportReason.WRONG_PRICE to "Wrong price",
    ReportReason.NOT_ON_MENU to "Not on menu",
    ReportReason.SPAM to "Spam",
    ReportReason.INAPPROPRIATE to "Inappropriate",
    ReportReason.OTHER to "Other",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReportBottomSheet(
    menuItemName: String,
    onDismiss: () -> Unit,
    onSubmit: (ReportReason, String?) -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var selectedReason by remember { mutableStateOf(ReportReason.WRONG_PRICE) }
    var comment by remember { mutableStateOf("") }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp, vertical = 8.dp),
        ) {
            Text(
                "Report this price",
                fontSize = 18.sp,
                modifier = Modifier.padding(bottom = 4.dp),
            )
            Text(
                menuItemName,
                fontSize = 12.sp,
                modifier = Modifier.padding(bottom = 16.dp),
            )
            REASON_ORDER.forEach { (reason, label) ->
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .fillMaxWidth()
                        .selectable(
                            selected = selectedReason == reason,
                            onClick = { selectedReason = reason },
                        )
                        .padding(vertical = 6.dp),
                ) {
                    RadioButton(
                        selected = selectedReason == reason,
                        onClick = { selectedReason = reason },
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(label, fontSize = 14.sp)
                }
            }
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = comment,
                onValueChange = { comment = it },
                label = { Text("Comment (optional)") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 2,
                maxLines = 4,
            )
            Spacer(Modifier.height(16.dp))
            Button(
                onClick = { onSubmit(selectedReason, comment) },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Submit report")
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
fun DifferentPriceDialog(
    menuItemName: String,
    currentPriceCents: Int,
    onDismiss: () -> Unit,
    onSubmit: (Int) -> Unit,
) {
    var priceText by remember {
        mutableStateOf("%.2f".format(currentPriceCents / 100.0))
    }
    val cents = parsePriceToCents(priceText)
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Report different price") },
        text = {
            Column {
                Text(menuItemName, fontSize = 13.sp)
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = priceText,
                    onValueChange = { priceText = it.filter { c -> c.isDigit() || c == '.' } },
                    label = { Text("New price ($)") },
                    keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(
                        keyboardType = KeyboardType.Decimal,
                    ),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(
                enabled = cents != null && cents > 0,
                onClick = { cents?.let(onSubmit) },
            ) { Text("Submit") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
    )
}

@Composable
fun RateRestaurantDialog(
    restaurantName: String,
    onDismiss: () -> Unit,
    onSubmit: (score: Int, comment: String?) -> Unit,
) {
    var score by remember { mutableStateOf(0) }
    var comment by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Rate $restaurantName") },
        text = {
            Column {
                Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                    repeat(5) { idx ->
                        val filled = idx < score
                        IconButton(onClick = { score = idx + 1 }) {
                            Icon(
                                imageVector = if (filled) Icons.Default.Star else Icons.Default.StarBorder,
                                contentDescription = "${idx + 1} star",
                            )
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = comment,
                    onValueChange = { comment = it },
                    label = { Text("Comment (optional)") },
                    minLines = 2,
                    maxLines = 4,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(
                enabled = score in 1..5,
                onClick = { onSubmit(score, comment) },
                colors = ButtonDefaults.textButtonColors(),
            ) { Text("Submit") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
    )
}

private fun parsePriceToCents(text: String): Int? {
    val t = text.trim()
    if (t.isEmpty()) return null
    val v = t.toDoubleOrNull() ?: return null
    if (v < 0) return null
    return (v * 100).toInt()
}
