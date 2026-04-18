package com.brokenlunch.gr.ui.submit

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.brokenlunch.gr.ui.theme.DisputedBg
import com.brokenlunch.gr.ui.theme.DisputedText
import com.brokenlunch.gr.ui.theme.HumanVerifiedBg
import com.brokenlunch.gr.ui.theme.HumanVerifiedText

@Composable
fun EditingScreen(
    restaurantName: String?,
    items: List<EditableItem>,
    parseWarnings: List<String>,
    onNameChange: (Int, String) -> Unit,
    onPriceChange: (Int, String) -> Unit,
    onDelete: (Int) -> Unit,
    onAddManual: () -> Unit,
    onRetake: () -> Unit,
    onSubmitAll: () -> Unit,
) {
    val validCount = items.count { it.isValid() }

    Column(Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp),
        ) {
            Text(
                restaurantName ?: "Review menu items",
                fontSize = 16.sp,
                fontWeight = FontWeight.Medium,
            )
            Text(
                "Edit names and prices, then submit.",
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        HorizontalDivider()

        if (parseWarnings.isNotEmpty()) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(DisputedBg)
                    .padding(horizontal = 16.dp, vertical = 8.dp),
            ) {
                parseWarnings.forEach { w ->
                    Text(w, fontSize = 11.sp, color = DisputedText)
                }
            }
        }

        LazyColumn(
            modifier = Modifier.weight(1f),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(
                horizontal = 12.dp, vertical = 8.dp,
            ),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(items, key = { it.clientId }) { item ->
                val index = items.indexOf(item)
                ItemCard(
                    item = item,
                    onNameChange = { onNameChange(index, it) },
                    onPriceChange = { onPriceChange(index, it) },
                    onDelete = { onDelete(index) },
                )
            }
            item {
                OutlinedButton(
                    onClick = onAddManual,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 8.dp),
                ) {
                    Icon(Icons.Default.Add, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("Add manual item", fontSize = 13.sp)
                }
            }
        }

        HorizontalDivider()
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp),
        ) {
            TextButton(onClick = onRetake) {
                Icon(Icons.Default.CameraAlt, contentDescription = null)
                Spacer(Modifier.width(4.dp))
                Text("Retake")
            }
            Spacer(Modifier.weight(1f))
            Button(
                onClick = onSubmitAll,
                enabled = validCount > 0,
            ) {
                Text(
                    if (validCount == 0) "Submit" else "Submit all ($validCount)",
                    fontSize = 14.sp,
                )
            }
        }
    }
}

@Composable
private fun ItemCard(
    item: EditableItem,
    onNameChange: (String) -> Unit,
    onPriceChange: (String) -> Unit,
    onDelete: () -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                ConfidenceBadge(item)
                Spacer(Modifier.weight(1f))
                IconButton(onClick = onDelete, modifier = Modifier.width(32.dp).height(32.dp)) {
                    Icon(
                        Icons.Default.Close,
                        contentDescription = "Remove",
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Spacer(Modifier.height(4.dp))
            OutlinedTextField(
                value = item.name,
                onValueChange = onNameChange,
                label = { Text("Item name") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = item.priceText,
                onValueChange = { raw ->
                    onPriceChange(raw.filter { c -> c.isDigit() || c == '.' })
                },
                label = { Text("Price ($)") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun ConfidenceBadge(item: EditableItem) {
    val (bg, fg, label) = when {
        item.confidence == null -> Triple(Color(0xFFEEEEEE), Color(0xFF444444), "Manual")
        item.needsReview() -> Triple(DisputedBg, DisputedText, "Needs review")
        else -> Triple(HumanVerifiedBg, HumanVerifiedText, "AI parsed")
    }
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(bg)
            .padding(horizontal = 8.dp, vertical = 3.dp),
    ) {
        Text(label, fontSize = 10.sp, fontWeight = FontWeight.Medium, color = fg)
    }
}
