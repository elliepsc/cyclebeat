import type { ApiFailure } from "../api/sessions";

export function ErrorNotice({ error }: { error: ApiFailure }) {
  if (error.kind === "network") {
    return (
      <div role="alert" className="notice notice--error">
        <strong>Cannot reach the API.</strong> Check your connection and that the API is running,
        then try again.
      </div>
    );
  }
  if (error.kind === "timeout") {
    return (
      <div role="alert" className="notice notice--error">
        <strong>The API did not answer within {Math.round(error.afterMs / 1000)} seconds.</strong>{" "}
        Try again in a moment.
      </div>
    );
  }
  return (
    <div role="alert" className="notice notice--error">
      <strong>
        {error.title} ({error.status})
      </strong>
      {error.detail && <p>{error.detail}</p>}
      {error.reasons.length > 0 && (
        <>
          <p>Reasons returned by the API:</p>
          <ul>
            {error.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
