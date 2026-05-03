const MAX_ALERT_NOTE_LENGTH = 2000;

function AlertNotesPanel({
  alertId,
  noteDraft,
  notes,
  isLoadingNotes,
  isAddingNote,
  onDraftChange,
  onAddNote,
  formatNoteTimestamp,
}) {
  return (
    <div style={{ marginTop: "24px" }}>
      <strong>Analyst Notes:</strong>
      <div style={{ marginTop: "10px" }}>
        <textarea
          value={noteDraft}
          onChange={(e) => onDraftChange(e.target.value)}
          maxLength={MAX_ALERT_NOTE_LENGTH}
          placeholder="Add investigation notes..."
          style={{
            width: "100%",
            minHeight: "96px",
            padding: "10px 12px",
            borderRadius: "10px",
            border: "1px solid #334155",
            backgroundColor: "#111827",
            color: "#e5e7eb",
            resize: "vertical",
            boxSizing: "border-box",
            fontSize: "13px",
          }}
        />
        <div
          style={{
            marginTop: "8px",
            fontSize: "12px",
            color: "#94a3b8",
            textAlign: "right",
          }}
        >
          {noteDraft.length} / {MAX_ALERT_NOTE_LENGTH}
        </div>
        <button
          type="button"
          onClick={() => onAddNote(alertId)}
          disabled={isAddingNote}
          style={{
            marginTop: "10px",
            padding: "8px 12px",
            borderRadius: "8px",
            border: "1px solid rgba(59, 130, 246, 0.35)",
            backgroundColor: "rgba(37, 99, 235, 0.18)",
            color: "#bfdbfe",
            fontWeight: "700",
            cursor: isAddingNote ? "not-allowed" : "pointer",
            opacity: isAddingNote ? 0.7 : 1,
          }}
        >
          {isAddingNote ? "Adding..." : "Add Note"}
        </button>
      </div>

      <div style={{ marginTop: "14px" }}>
        {isLoadingNotes ? (
          <div style={{ fontSize: "12px", opacity: 0.7 }}>Loading notes...</div>
        ) : notes.length > 0 ? (
          notes.map((note) => (
            <div
              key={note.id}
              style={{
                marginTop: "8px",
                padding: "10px 12px",
                borderRadius: "10px",
                backgroundColor: "#111827",
                border: "1px solid #1f2937",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "12px",
                  marginBottom: "6px",
                  fontSize: "12px",
                  color: "#94a3b8",
                }}
              >
                <span>{note.author}</span>
                <span>{formatNoteTimestamp(note.created_at)}</span>
              </div>
              <div style={{ fontSize: "13px", lineHeight: "1.55", color: "#e5e7eb" }}>
                {note.note_text}
              </div>
            </div>
          ))
        ) : (
          <div style={{ fontSize: "12px", opacity: 0.7 }}>
            No notes yet. Add the first note.
          </div>
        )}
      </div>
    </div>
  );
}

export default AlertNotesPanel;
