package com.brokenlunch.gr.data

import retrofit2.HttpException
import kotlin.coroutines.cancellation.CancellationException

sealed class ApiResult<out T> {
    data class Success<T>(val data: T) : ApiResult<T>()
    data class HttpError(val code: Int, val message: String?) : ApiResult<Nothing>()
    data class NetworkError(val cause: Throwable) : ApiResult<Nothing>()

    inline fun <R> map(transform: (T) -> R): ApiResult<R> = when (this) {
        is Success -> Success(transform(data))
        is HttpError -> this
        is NetworkError -> this
    }

    fun getOrNull(): T? = (this as? Success)?.data
}

suspend fun <T> safeApiCall(block: suspend () -> T): ApiResult<T> = try {
    ApiResult.Success(block())
} catch (e: CancellationException) {
    throw e
} catch (e: HttpException) {
    ApiResult.HttpError(e.code(), e.message())
} catch (e: Throwable) {
    ApiResult.NetworkError(e)
}
