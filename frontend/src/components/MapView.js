import React, { useEffect, useRef, useState } from "react";
import {
  ComposableMap,
  Geographies,
  Geography,
  Marker,
  ZoomableGroup
} from "react-simple-maps";
import {
  getBehavioralReputation,
  getExternalReputation,
  getReputationBadgeStyle,
} from "../utils/alertDisplay";
import SourceIpContext from "./SourceIpContext";

const geoUrl = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

function MapView({ alerts }) {
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [isInteractive, setIsInteractive] = useState(false);
  const mapContainerRef = useRef(null);
  const [position, setPosition] = useState({
    coordinates: [0, 0],
    zoom: 0.7
  });
  const selectedExternalReputation = getExternalReputation(selectedAlert);
  const selectedBehavioralReputation = getBehavioralReputation(selectedAlert);

  useEffect(() => {
    const handlePointerDown = (event) => {
      if (!mapContainerRef.current?.contains(event.target)) {
        setIsInteractive(false);
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  }, []);

  return (
    <div
      ref={mapContainerRef}
      style={{
        width: "100%",
        maxWidth: "1400px",
        margin: "0 auto",
        height: "480px",
        position: "relative",
        background: "#0f172a",
        border: "1px solid #334155",
        borderRadius: "14px",
        overflow: "hidden",
        overscrollBehavior: isInteractive ? "contain" : "auto",
        touchAction: isInteractive ? "none" : "auto"
      }}
    >
      <div
        style={{
          position: "absolute",
          top: "16px",
          left: "16px",
          display: "flex",
          gap: "8px",
          zIndex: 20
        }}
      >
        <button
          onClick={(event) => {
            event.stopPropagation();
            setPosition((prev) => ({
              ...prev,
              zoom: Math.min(prev.zoom * 1.5, 8)
            }));
          }}
          style={zoomButtonStyle}
        >
          +
        </button>

        <button
          onClick={(event) => {
            event.stopPropagation();
            setPosition((prev) => ({
              ...prev,
              zoom: Math.max(prev.zoom / 1.5, 0.7)
            }));
          }}
          style={zoomButtonStyle}
        >
          -
        </button>

        <button
          onClick={(event) => {
            event.stopPropagation();
            setPosition({ coordinates: [0, 0], zoom: 0.7 });
            setIsInteractive(false);
          }}
          style={zoomButtonStyle}
        >
          Reset
        </button>
      </div>

      {!isInteractive && (
        <button
          type="button"
          onClick={() => setIsInteractive(true)}
          style={mapOverlayStyle}
          aria-label="Activate map interactions"
        >
          Click to interact with map
        </button>
      )}

      <ComposableMap
        projection="geoMercator"
        projectionConfig={{
          scale: 145
        }}
        width={980}
        height={420}
        style={{
          width: "100%",
          height: "100%",
          background: "#0f172a"
        }}
        onClick={() => setIsInteractive(true)}
        onWheel={(e) => {
          if (isInteractive) {
            e.stopPropagation();
          }
        }}
      >
        <ZoomableGroup
          center={position.coordinates}
          zoom={position.zoom}
          minZoom={0.7}
          maxZoom={8}
          filterZoomEvent={(event) =>
            isInteractive &&
            (event.type === "wheel" ||
              event.type === "mousedown" ||
              event.type === "mousemove" ||
              event.type === "touchmove")
          }
          onMoveEnd={({ coordinates, zoom }) => {
            setPosition({ coordinates, zoom });
          }}
        >
          <Geographies geography={geoUrl}>
            {({ geographies }) =>
              geographies.map((geo) => (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  style={{
                    default: {
                      fill: "#1e293b",
                      stroke: "#334155",
                      strokeWidth: 0.55,
                      outline: "none"
                    },
                    hover: {
                      fill: "#1e293b",
                      stroke: "#334155",
                      strokeWidth: 0.7,
                      outline: "none"
                    },
                    pressed: {
                      fill: "#1e293b",
                      stroke: "#334155",
                      strokeWidth: 0.7,
                      outline: "none"
                    }
                  }}
                />
              ))
            }
          </Geographies>

          {alerts.map((alert, index) => {
            if (alert.latitude == null || alert.longitude == null) return null;

            const markerColor =
              alert.severity === "high"
                ? "#ef4444"
                : alert.severity === "medium"
                  ? "#f59e0b"
                  : "#22c55e";

            return (
              <Marker
                key={index}
                coordinates={[alert.longitude, alert.latitude]}
                onClick={() => {
                  setIsInteractive(true);
                  setSelectedAlert(alert);
                }}
              >
                <g style={{ cursor: "pointer" }}>
                  <circle
                    r={7}
                    fill={markerColor}
                    stroke="#fff"
                    strokeWidth={1}
                  />

                  <circle
                    r={14}
                    fill="none"
                    stroke={markerColor}
                    strokeWidth={2}
                    opacity={0.6}
                  >
                    <animate
                      attributeName="r"
                      from="10"
                      to="26"
                      dur="1.6s"
                      repeatCount="indefinite"
                    />
                    <animate
                      attributeName="opacity"
                      from="0.6"
                      to="0"
                      dur="1.6s"
                      repeatCount="indefinite"
                    />
                  </circle>
                </g>
              </Marker>
            );
          })}
        </ZoomableGroup>
      </ComposableMap>

      {selectedAlert && (
        <div
          data-testid="map-attack-details-popup"
          style={attackDetailsPopupStyle}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center"
            }}
          >
            <strong style={{ fontSize: "16px" }}>Attack Details</strong>
            <button
              onClick={() => setSelectedAlert(null)}
              style={{
                background: "transparent",
                border: "none",
                color: "#9ca3af",
                cursor: "pointer",
                fontSize: "16px"
              }}
            >
              x
            </button>
          </div>

          <p style={{ marginTop: "10px" }}>
            <strong>IP:</strong> {selectedAlert.source_ip}
          </p>
          <p>
            <strong>Location:</strong>{" "}
            {selectedAlert.city && selectedAlert.country
              ? `${selectedAlert.city}, ${selectedAlert.country}`
              : "Location unavailable"}
          </p>
          <p>
            <strong>Severity:</strong> {selectedAlert.severity}
          </p>
          <p>
            <strong>Message:</strong> {selectedAlert.message}
          </p>
          <p>
            <strong>External Threat Intelligence Reputation:</strong>{" "}
            <span
              style={{
                ...mapReputationBadgeStyle,
                ...getReputationBadgeStyle(selectedExternalReputation.label),
              }}
            >
              {selectedExternalReputation.label} ({selectedExternalReputation.score ?? "n/a"})
            </span>
          </p>
          <p style={{ marginTop: "8px" }}>
            Source: {selectedExternalReputation.source}
          </p>
          <p style={{ marginTop: "8px" }}>
            {selectedExternalReputation.summary}
          </p>
          <p>
            <strong>Behavioral Reputation:</strong>{" "}
            <span
              style={{
                ...mapReputationBadgeStyle,
                ...getReputationBadgeStyle(selectedBehavioralReputation.label),
              }}
            >
              {selectedBehavioralReputation.label} ({selectedBehavioralReputation.score})
            </span>
          </p>
          <p style={{ marginTop: "8px" }}>
            {selectedBehavioralReputation.summary}
          </p>
          <p>
            <strong>Response Action:</strong>{" "}
            {selectedAlert.response_action || "Not set"}
          </p>
          <p>
            <strong>Response Status:</strong>{" "}
            {selectedAlert.response_status || "Not set"}
          </p>
          <SourceIpContext sourceIp={selectedAlert.source_ip} compact />
        </div>
      )}
    </div>
  );
}

const mapOverlayStyle = {
  position: "absolute",
  inset: 0,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "rgba(15, 23, 42, 0.18)",
  color: "#e5e7eb",
  border: "none",
  fontSize: "13px",
  fontWeight: "700",
  letterSpacing: "0.02em",
  cursor: "pointer",
  zIndex: 15,
};

const zoomButtonStyle = {
  background: "#111827",
  color: "#e5e7eb",
  border: "1px solid #374151",
  borderRadius: "8px",
  padding: "8px 12px",
  cursor: "pointer"
};

const attackDetailsPopupStyle = {
  position: "absolute",
  top: "20px",
  right: "20px",
  width: "min(360px, calc(100% - 40px))",
  maxWidth: "360px",
  maxHeight: "calc(100% - 40px)",
  overflowY: "auto",
  overflowX: "hidden",
  padding: "14px",
  background: "#111827",
  border: "1px solid #374151",
  borderRadius: "10px",
  color: "#e5e7eb",
  boxShadow: "0 4px 12px rgba(0, 0, 0, 0.35)",
  zIndex: 10,
  boxSizing: "border-box",
  overscrollBehavior: "contain",
};

const mapReputationBadgeStyle = {
  display: "inline-block",
  padding: "4px 8px",
  borderRadius: "999px",
  fontSize: "11px",
  fontWeight: "600",
};

export default MapView;
