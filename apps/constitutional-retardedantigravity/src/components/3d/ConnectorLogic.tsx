import { useAppStore } from '../../stores/useAppStore';
import { useThree, useFrame } from '@react-three/fiber';
import * as THREE from 'three';

// This component MUST be inside the Canvas to access 3D context,
// BUT it renders nothing in 3D.
// Instead, it updates a global SVG overlay or store coordinates.
// However, the user wants the Connector to be in the "2D Overlay".
// So we will trigger an update to a separate 2D component via store or event.

// Alternative: We can compute the screen coords here and pass them to a Zustand store,
// which the 2D overlay consumes.

export function ConnectorLogic() {
    const { activeSourceId, sources, setConnectorCoords } = useAppStore();
    const { camera, size } = useThree();

    useFrame(() => {
        if (!activeSourceId) {
            setConnectorCoords(null);
            return;
        }

        const sourceIndex = sources.findIndex(s => s.id === activeSourceId);
        if (sourceIndex === -1) return;

        // Calculate 3D position (matching EvidenceDeck logic)
        const deckOffset = 2.5;
        const cardLocalX = (sourceIndex - 1.5) * 1.8;
        const x = deckOffset + cardLocalX;
        const y = 0.2;
        const z = 1.5;

        const vec = new THREE.Vector3(x, y, z);

        // Project to 2D screen space
        vec.project(camera);

        const x2 = (vec.x * .5 + .5) * size.width;
        const y2 = (-(vec.y * .5) + .5) * size.height;

        console.log('Sending Coords:', x2, y2);
        // Send to store for 2D rendering
        setConnectorCoords({ x: x2, y: y2 });
    });

    return null;
}
