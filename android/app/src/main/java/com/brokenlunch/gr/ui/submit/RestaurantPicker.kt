package com.brokenlunch.gr.ui.submit

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.brokenlunch.gr.data.model.MenuStatus
import com.brokenlunch.gr.data.model.RestaurantNearby
import com.brokenlunch.gr.ui.common.formatDistanceMeters
import com.brokenlunch.gr.ui.map.categoryEmoji
import com.brokenlunch.gr.ui.theme.AiParsedBg
import com.brokenlunch.gr.ui.theme.AiParsedText
import com.brokenlunch.gr.ui.theme.EmptyBg

@Composable
fun RestaurantPicker(
    query: String,
    restaurants: List<RestaurantNearby>,
    onQueryChange: (String) -> Unit,
    onSelect: (RestaurantNearby) -> Unit,
) {
    val filtered = if (query.isBlank()) restaurants
    else restaurants.filter { it.name.contains(query, ignoreCase = true) }

    Column(Modifier.fillMaxSize()) {
        Text(
            "Which restaurant?",
            fontSize = 18.sp,
            fontWeight = FontWeight.Medium,
            modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 4.dp),
        )
        Text(
            "Pick a place to add menu items for.",
            fontSize = 12.sp,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = query,
            onValueChange = onQueryChange,
            leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
            trailingIcon = {
                if (query.isNotEmpty()) {
                    IconButton(onClick = { onQueryChange("") }) {
                        Icon(Icons.Default.Close, contentDescription = "Clear")
                    }
                }
            },
            placeholder = { Text("Search nearby", fontSize = 13.sp) },
            singleLine = true,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
        )
        Spacer(Modifier.height(8.dp))
        HorizontalDivider()
        if (filtered.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(
                    if (restaurants.isEmpty()) "Loading nearby restaurants…" else "No matches.",
                    fontSize = 13.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        } else {
            LazyColumn(Modifier.fillMaxSize()) {
                items(filtered, key = { it.id }) { r ->
                    PickerRow(r, onClick = { onSelect(r) })
                    HorizontalDivider(color = androidx.compose.ui.graphics.Color(0x11000000))
                }
            }
        }
    }
}

@Composable
private fun PickerRow(r: RestaurantNearby, onClick: () -> Unit) {
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
            Text(categoryEmoji(r.category), fontSize = 14.sp)
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
        if (r.menuStatus == MenuStatus.EMPTY) {
            Box(
                modifier = Modifier
                    .clip(androidx.compose.foundation.shape.RoundedCornerShape(999.dp))
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
}
