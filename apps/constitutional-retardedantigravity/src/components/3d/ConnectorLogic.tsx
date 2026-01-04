import { useAppStore } from '../../stores/useAppStore';
import { useThree, useFrame } from '@react-three/fiber';
import * as THREE from 'three';

// This component runs inside the Canvas to project 3D card positions to 2D screen coords.
// It updates the Zustand store, which the 2D ConnectorOverlay reads.

export function ConnectorLogic() {
    const { activeSourceId, sources, setConnectorCoords } = useAppStore();
    const { camera, size } = useThree();

    useFrame((state) => {
        // Heartbeat log every 60 frames (~1 sec)
        if (state.clock.getElapsedTime() % 1 < 0.05) {
            console.log('ConnectorLogic Heartbeat. ActiveSource:', activeSourceId);
        }

        if (!activeSourceId) {
            setConnectorCoords(null);
            return;
        }

        const sourceIndex = sources.findIndex(s => s.id === activeSourceId);
        if (sourceIndex === -1) {
            console.log('ConnectorLogic: Source not found', activeSourceId);
            setConnectorCoords(null);
            return;
        }

        // Match the EvidenceDeck and SourceCard positioning:
        // EvidenceDeck is at [0, -1.5, 0]
        // Cards spread with: spread = 2.2, centerOffset = (total-1)/2, x = (index - centerOffset) * spread
        // Active card moves to z=2, y=0.5
        const total = sources.length;
        const spread = 2.2;
        const centerOffset = (total - 1) / 2;

        const x = (sourceIndex - centerOffset) * spread;
        const y = -1.5 + 0.5; // EvidenceDeck y offset + active card y
        const z = 2; // Active card z position

        const vec = new THREE.Vector3(x, y, z);
        vec.project(camera);

        // Convert NDC to screen pixels
        const x2 = (vec.x * 0.5 + 0.5) * size.width;
        const y2 = (-(vec.y * 0.5) + 0.5) * size.height;

        setConnectorCoords({ x: x2, y: y2 });
    });

    return null;
}
