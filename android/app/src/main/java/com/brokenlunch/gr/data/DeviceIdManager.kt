package com.brokenlunch.gr.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.util.UUID
import java.util.concurrent.atomic.AtomicReference
import javax.inject.Inject
import javax.inject.Singleton

private val Context.deviceIdDataStore: DataStore<Preferences> by preferencesDataStore(name = "device_prefs")

private val DEVICE_ID_KEY = stringPreferencesKey("device_id")

@Singleton
class DeviceIdManager @Inject constructor(
    @ApplicationContext context: Context,
) {
    private val dataStore: DataStore<Preferences> = context.deviceIdDataStore
    private val cached = AtomicReference<String?>(null)
    private val initMutex = Mutex()

    suspend fun getDeviceId(): String {
        cached.get()?.let { return it }
        return initMutex.withLock {
            cached.get()?.let { return@withLock it }
            val existing = dataStore.data.first()[DEVICE_ID_KEY]
            val id = existing ?: UUID.randomUUID().toString().also { generated ->
                dataStore.edit { it[DEVICE_ID_KEY] = generated }
            }
            cached.set(id)
            id
        }
    }

    fun getDeviceIdBlocking(): String = runBlocking { getDeviceId() }
}
