import { useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { useAppStore } from '../../stores/useAppStore';
import * as THREE from 'three';

export function ConnectorLines() {
    const { activeSourceId, citationTarget, sources } = useAppStore();
    const lineRef = useRef<THREE.Line>(null);
    const { camera, size } = useThree();

    useFrame(() => {
        if (!activeSourceId || !citationTarget || !lineRef.current) {
            if (lineRef.current) lineRef.current.visible = false;
            return;
        }

        // 1. Get Start Point (2D DOM -> 3D World)
        // We want the center of the citation button
        const x = citationTarget.left + citationTarget.width / 2;
        const y = citationTarget.top + citationTarget.height / 2;

        // Normalize to -1 to +1 range
        const ndcX = (x / size.width) * 2 - 1;
        const ndcY = -(y / size.height) * 2 + 1;

        // Unproject to find a point in 3D space near the camera plane
        const vector = new THREE.Vector3(ndcX, ndcY, 0.5);
        vector.unproject(camera);

        // Instead of sticking to the camera plane, we want the line to start "from the text"
        // which effectively means a point in space that lines up with the text.
        // We can pick a Z-depth that feels like the "glass plane" of the UI, e.g., Z=2
        const dir = vector.sub(camera.position).normalize();
        const distance = (2 - camera.position.z) / dir.z;
        const startPos = camera.position.clone().add(dir.multiplyScalar(distance));


        // 2. Get End Point (3D Card Position)
        // We need to know where the active card is.
        // Based on EvidenceDeck position (2.5) + SourceCard logic: xPos = (index - 1.5) * 1.8;
        const sourceIndex = sources.findIndex(s => s.id === activeSourceId);
        if (sourceIndex === -1) return;

        const deckOffset = 2.5;
        const cardLocalX = (sourceIndex - 1.5) * 1.8;
        const endX = deckOffset + cardLocalX;

        const endY = 0.2; // Active Y
        const endZ = 1.5; // Active Z

        // Update geometry
        const points = [startPos, new THREE.Vector3(endX, endY, endZ)];
        lineRef.current.geometry.setFromPoints(points);
        lineRef.current.visible = true;
    });

    return (
        <line ref={lineRef}>
            <bufferGeometry />
            <lineBasicMaterial color="#00f3ff" linewidth={2} transparent opacity={0.6} />
        </line>
    );
}
