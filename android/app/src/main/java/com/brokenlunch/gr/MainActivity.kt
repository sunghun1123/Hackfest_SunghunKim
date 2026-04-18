package com.brokenlunch.gr

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.brokenlunch.gr.ui.navigation.BrokenLunchNavHost
import com.brokenlunch.gr.ui.theme.BrokenLunchTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            BrokenLunchTheme {
                BrokenLunchNavHost()
            }
        }
    }
}
