package com.brokenlunch.gr.ui.navigation

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.AddAPhoto
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.brokenlunch.gr.ui.detail.DETAIL_ARG_ID
import com.brokenlunch.gr.ui.detail.RestaurantDetailScreen
import com.brokenlunch.gr.ui.list.ListScreen
import com.brokenlunch.gr.ui.map.MapScreen
import com.brokenlunch.gr.ui.profile.ProfileScreen
import com.brokenlunch.gr.ui.recommend.RecommendScreen
import com.brokenlunch.gr.ui.submit.SUBMIT_ARG_RESTAURANT_ID
import com.brokenlunch.gr.ui.submit.SubmitScreen
import com.brokenlunch.gr.ui.theme.SurviveBorder
import com.brokenlunch.gr.ui.theme.SurviveText

object Routes {
    const val MAP = "map"
    const val LIST = "list"
    const val DETAIL = "restaurant/{$DETAIL_ARG_ID}"
    const val SUBMIT = "submit?$SUBMIT_ARG_RESTAURANT_ID={$SUBMIT_ARG_RESTAURANT_ID}"
    const val PROFILE = "profile"
    const val RECOMMEND = "recommend"

    fun detail(id: String) = "restaurant/$id"
    fun submit(restaurantId: String? = null): String =
        if (restaurantId == null) "submit?$SUBMIT_ARG_RESTAURANT_ID=none"
        else "submit?$SUBMIT_ARG_RESTAURANT_ID=$restaurantId"
}

private data class Tab(
    val route: String,
    val label: String,
    val icon: ImageVector,
)

private val BOTTOM_TABS = listOf(
    Tab(Routes.MAP, "Map", Icons.Default.Map),
    Tab(Routes.LIST, "List", Icons.AutoMirrored.Filled.List),
    // Submit is a center FAB — rendered separately
    Tab(Routes.RECOMMEND, "Recommend", Icons.Default.AutoAwesome),
    Tab(Routes.PROFILE, "Profile", Icons.Default.Person),
)

@Composable
fun BrokenLunchNavHost(
    navController: NavHostController = rememberNavController(),
) {
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route
    val showBottomBar = currentRoute in setOf(
        Routes.MAP, Routes.LIST, Routes.PROFILE, Routes.RECOMMEND,
    )

    Scaffold(
        bottomBar = {
            if (showBottomBar) {
                BottomBar(
                    currentRoute = currentRoute,
                    onTabClick = { route -> navigateToTab(navController, route) },
                    onSubmitClick = { navController.navigate(Routes.submit()) },
                )
            }
        },
    ) { inner ->
        NavHost(
            navController = navController,
            startDestination = Routes.MAP,
            modifier = Modifier
                .fillMaxSize()
                .padding(inner),
        ) {
            composable(Routes.MAP) {
                MapScreen(
                    onRestaurantClick = { id -> navController.navigate(Routes.detail(id)) },
                )
            }
            composable(Routes.LIST) {
                ListScreen(
                    onRestaurantClick = { id -> navController.navigate(Routes.detail(id)) },
                )
            }
            composable(
                route = Routes.DETAIL,
                arguments = listOf(navArgument(DETAIL_ARG_ID) { type = NavType.StringType }),
            ) {
                RestaurantDetailScreen(
                    onBack = { navController.popBackStack() },
                    onSubmitClick = { id -> navController.navigate(Routes.submit(id)) },
                )
            }
            composable(
                route = Routes.SUBMIT,
                arguments = listOf(
                    navArgument(SUBMIT_ARG_RESTAURANT_ID) {
                        type = NavType.StringType
                        defaultValue = "none"
                    },
                ),
            ) {
                SubmitScreen(
                    onExit = { navController.popBackStack() },
                )
            }
            composable(Routes.PROFILE) { ProfileScreen() }
            composable(Routes.RECOMMEND) { RecommendScreen() }
        }
    }
}

private fun navigateToTab(navController: NavHostController, route: String) {
    navController.navigate(route) {
        popUpTo(navController.graph.findStartDestination().id) {
            saveState = true
        }
        launchSingleTop = true
        restoreState = true
    }
}

@Composable
private fun BottomBar(
    currentRoute: String?,
    onTabClick: (String) -> Unit,
    onSubmitClick: () -> Unit,
) {
    NavigationBar {
        // Map + List on left
        BOTTOM_TABS.take(2).forEach { tab ->
            NavigationBarItem(
                selected = currentRoute == tab.route,
                onClick = { onTabClick(tab.route) },
                icon = { Icon(tab.icon, contentDescription = null) },
                label = { Text(tab.label, fontSize = 10.sp) },
            )
        }
        // Center FAB-style Submit
        NavigationBarItem(
            selected = false,
            onClick = onSubmitClick,
            icon = {
                Box(
                    modifier = Modifier
                        .size(40.dp)
                        .clip(CircleShape)
                        .background(SurviveBorder),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        Icons.Default.AddAPhoto,
                        contentDescription = "Submit",
                        tint = MaterialTheme.colorScheme.surface,
                    )
                }
            },
            label = { Text("Submit", fontSize = 10.sp, fontWeight = FontWeight.Medium, color = SurviveText) },
        )
        // Recommend + Profile on right
        BOTTOM_TABS.drop(2).forEach { tab ->
            NavigationBarItem(
                selected = currentRoute == tab.route,
                onClick = { onTabClick(tab.route) },
                icon = { Icon(tab.icon, contentDescription = null) },
                label = { Text(tab.label, fontSize = 10.sp) },
            )
        }
    }
}
