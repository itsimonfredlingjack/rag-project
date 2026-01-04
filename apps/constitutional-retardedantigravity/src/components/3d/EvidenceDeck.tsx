import { useAppStore } from '../../stores/useAppStore';
import { SourceCard } from './SourceCard';

export function EvidenceDeck() {
    const sources = useAppStore(state => state.sources);

    // Position cards in the lower portion of the 3D space
    // Camera is at [0, 2, 8], looking forward
    // Cards should be below eye level and spread across the floor
    return (
        <group position={[0, -1.5, 0]}>
            {sources.map((source, index) => (
                <SourceCard
                    key={source.id}
                    source={source}
                    index={index}
                    total={sources.length}
                />
            ))}
        </group>
    );
}
