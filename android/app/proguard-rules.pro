# Moshi generated adapters are referenced reflectively by the codegen runtime.
-keep class **JsonAdapter { *; }
-keepclassmembers class ** {
    @com.squareup.moshi.FromJson *;
    @com.squareup.moshi.ToJson *;
}
# Kotlin metadata for Moshi reflective fallback (not usually needed with codegen).
-keep class kotlin.Metadata { *; }
