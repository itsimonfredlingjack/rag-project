import { useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Text } from '@react-three/drei';
import * as THREE from 'three';
import { useAppStore } from '../../stores/useAppStore';

interface Source {
    id: string;
    title: string;
    type: string;
    date?: string;
    snippet?: string;
    relevance?: number;
}

interface SourceCardProps {
    source: Source;
    index: number;
    total: number;
}

export function SourceCard({ source, index, total }: SourceCardProps) {
    const meshRef = useRef<THREE.Group>(null);
    const activeSourceId = useAppStore(state => state.activeSourceId);
    const setActiveSource = useAppStore(state => state.setActiveSource);

    const isActive = activeSourceId === source.id;
    const [hovered, setHovered] = useState(false);

    useFrame(() => {
        if (!meshRef.current) return;

        // Spread cards in a gentle arc across the floor
        const spread = 2.2;
        const centerOffset = (total - 1) / 2;
        const xPos = (index - centerOffset) * spread;

        // Active cards come forward and up
        const targetZ = isActive ? 2 : (hovered ? 1 : 0);
        const targetY = isActive ? 0.5 : (hovered ? 0.2 : 0);
        const targetRotX = isActive ? -0.15 : (hovered ? -0.08 : 0);

        // Smooth lerp
        meshRef.current.position.x = THREE.MathUtils.lerp(meshRef.current.position.x, xPos, 0.08);
        meshRef.current.position.z = THREE.MathUtils.lerp(meshRef.current.position.z, targetZ, 0.08);
        meshRef.current.position.y = THREE.MathUtils.lerp(meshRef.current.position.y, targetY, 0.08);
        meshRef.current.rotation.x = THREE.MathUtils.lerp(meshRef.current.rotation.x, targetRotX, 0.08);
    });

    return (
        <group
            ref={meshRef}
            position={[(index - 1.5) * 2.2, 0, -15]} // Start far back
            onClick={() => setActiveSource(isActive ? null : source.id)}
            onPointerOver={() => setHovered(true)}
            onPointerOut={() => setHovered(false)}
        >
            {/* Card Body */}
            <mesh>
                <boxGeometry args={[1.8, 1.2, 0.08]} />
                <meshPhysicalMaterial
                    color={isActive ? "#0a2020" : "#0a0a0a"}
                    transparent
                    opacity={isActive ? 0.95 : 0.85}
                    roughness={0.3}
                    metalness={0.5}
                    emissive={isActive ? "#00f3ff" : "#000000"}
                    emissiveIntensity={isActive ? 0.15 : 0}
                />
            </mesh>

            {/* Title */}
            <Text
                position={[-0.8, 0.4, 0.06]}
                anchorX="left"
                anchorY="top"
                maxWidth={1.6}
                fontSize={0.11}
                font="/fonts/Inter-Medium.woff"
                color={isActive ? "#ffffff" : "#888888"}
            >
                {source.title}
            </Text>

            {/* Type Badge */}
            <Text
                position={[-0.8, 0.2, 0.06]}
                anchorX="left"
                fontSize={0.07}
                color="#00f3ff"
            >
                {source.type.toUpperCase()}
            </Text>

            {/* Snippet */}
            <Text
                position={[-0.8, 0.05, 0.06]}
                anchorX="left"
                anchorY="top"
                maxWidth={1.6}
                fontSize={0.06}
                color="#666666"
                lineHeight={1.3}
            >
                {source.snippet?.substring(0, 60)}...
            </Text>

            {/* Glow Border (Active/Hover) */}
            {(isActive || hovered) && (
                <mesh position={[0, 0, -0.01]}>
                    <boxGeometry args={[1.85, 1.25, 0.02]} />
                    <meshBasicMaterial color="#00f3ff" transparent opacity={isActive ? 0.4 : 0.2} />
                </mesh>
            )}
        </group>
    );
}
