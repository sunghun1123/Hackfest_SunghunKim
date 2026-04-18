package com.brokenlunch.gr.data.api

import com.brokenlunch.gr.data.DeviceIdManager
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class DeviceIdInterceptor @Inject constructor(
    private val deviceIdManager: DeviceIdManager,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        if (request.header("X-Device-Id") != null) {
            return chain.proceed(request)
        }
        val withHeader = request.newBuilder()
            .header("X-Device-Id", deviceIdManager.getDeviceIdBlocking())
            .build()
        return chain.proceed(withHeader)
    }
}
