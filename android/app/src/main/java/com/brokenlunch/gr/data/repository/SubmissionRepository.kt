package com.brokenlunch.gr.data.repository

import com.brokenlunch.gr.data.ApiResult
import com.brokenlunch.gr.data.api.BrokenLunchApi
import com.brokenlunch.gr.data.model.ConfirmationRequest
import com.brokenlunch.gr.data.model.ConfirmationResponse
import com.brokenlunch.gr.data.model.ReportReason
import com.brokenlunch.gr.data.model.ReportRequest
import com.brokenlunch.gr.data.model.ReportResponse
import com.brokenlunch.gr.data.model.SubmissionRequest
import com.brokenlunch.gr.data.model.SubmissionResponse
import com.brokenlunch.gr.data.safeApiCall
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class SubmissionRepository @Inject constructor(
    private val api: BrokenLunchApi,
) {
    suspend fun submit(body: SubmissionRequest): ApiResult<SubmissionResponse> = safeApiCall {
        api.postSubmission(body)
    }

    suspend fun confirm(menuItemId: String, isAgreement: Boolean, reportedPrice: Int? = null): ApiResult<ConfirmationResponse> = safeApiCall {
        api.postConfirmation(ConfirmationRequest(menuItemId, isAgreement, reportedPrice))
    }

    suspend fun report(menuItemId: String, reason: ReportReason, comment: String? = null): ApiResult<ReportResponse> = safeApiCall {
        api.postReport(ReportRequest(menuItemId, reason, comment))
    }
}
