import { useAppStore } from '../../stores/useAppStore';

export function ConnectorOverlay() {
    const { activeSourceId, citationTarget, connectorCoords } = useAppStore();

    if (!activeSourceId || !citationTarget || !connectorCoords) return null;

    // Calculate start point (center of citation button)
    const x1 = citationTarget.left + citationTarget.width / 2;
    const y1 = citationTarget.top + citationTarget.height / 2;

    // End point is from store (projected 3D position)
    const x2 = connectorCoords.x;
    const y2 = connectorCoords.y;

    return (
        <svg
            className="fixed inset-0 pointer-events-none z-[50] w-full h-full"
            style={{ overflow: 'visible' }}
        >
            <defs>
                <marker
                    id="dot"
                    viewBox="0 0 10 10"
                    refX="5"
                    refY="5"
                    markerWidth="4"
                    markerHeight="4"
                >
                    <circle cx="5" cy="5" r="5" fill="#00f3ff" />
                </marker>
            </defs>

            {/* Glow path */}
            <path
                d={`M ${x1} ${y1} C ${x1 + 50} ${y1}, ${x2 - 50} ${y2}, ${x2} ${y2}`}
                fill="none"
                stroke="#00f3ff"
                strokeWidth="3"
                strokeOpacity="0.3"
                filter="blur(4px)"
            />

            {/* Main line */}
            <path
                d={`M ${x1} ${y1} C ${x1 + 50} ${y1}, ${x2 - 50} ${y2}, ${x2} ${y2}`}
                fill="none"
                stroke="#00f3ff"
                strokeWidth="1.5"
                markerEnd="url(#dot)"
            />
        </svg>
    );
}
