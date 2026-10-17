export function safeErrorMessage(value: unknown, fallback?: string): string
export function apiErrorMessage(response: Response, fallback: string): Promise<string>
export function safeApiErrorMessage(body: unknown, fallback: string): string
