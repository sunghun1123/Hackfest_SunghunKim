package com.brokenlunch.gr

import android.app.Application
import com.brokenlunch.gr.data.DeviceIdManager
import dagger.hilt.android.HiltAndroidApp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltAndroidApp
class BrokenLunchApp : Application() {

    @Inject lateinit var deviceIdManager: DeviceIdManager

    override fun onCreate() {
        super.onCreate()
        CoroutineScope(Dispatchers.IO + SupervisorJob()).launch {
            deviceIdManager.getDeviceId()
        }
    }
}
