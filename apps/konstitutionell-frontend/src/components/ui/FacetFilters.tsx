import { useEffect, useState } from "react";
import { useAppStore } from "../../stores/useAppStore";
import { Filter, ChevronDown, ChevronUp, RotateCcw } from "lucide-react";

export function FacetFilters() {
  const {
    availableFacets,
    selectedAgencies,
    selectedDocTypes,
    yearStart,
    yearEnd,
    toggleAgencyFilter,
    toggleDocTypeFilter,
    setYearRange,
    clearFilters,
    fetchFacets,
  } = useAppStore();

  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    fetchFacets();
  }, [fetchFacets]);

  if (!availableFacets) return null;

  const totalActive = selectedAgencies.length + selectedDocTypes.length + (yearStart !== 1900 || yearEnd !== 2026 ? 1 : 0);

  return (
    <div className="w-full font-ui text-slate-300 mb-6 bg-[#11161B]/80 border border-white/5 rounded-2xl overflow-hidden backdrop-blur-md transition-all duration-200">
      {/* Header bar */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-5 py-3.5 flex items-center justify-between hover:bg-white/[0.01] transition-colors cursor-pointer text-sm"
      >
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-teal-400" />
          <span className="font-medium text-slate-200">Filtrera sökning</span>
          {totalActive > 0 && (
            <span className="px-2 py-0.5 text-[10px] font-mono font-bold bg-teal-500/10 text-teal-400 border border-teal-500/20 rounded-full">
              {totalActive} aktiv{totalActive > 1 ? "a" : ""}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 text-xs text-stone-500 hover:text-slate-300">
          <span>{isOpen ? "Dölj" : "Visa inställningar"}</span>
          {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {/* Expanded filters panel */}
      {isOpen && (
        <div className="px-5 pb-5 pt-3 border-t border-white/5 grid grid-cols-1 md:grid-cols-3 gap-6 bg-black/10">
          {/* Column 1: Authorities / Agencies */}
          <div className="flex flex-col gap-2">
            <span className="text-[10px] uppercase font-mono tracking-wider text-slate-500 font-semibold mb-1">
              Myndighet / Källa
            </span>
            <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto custom-scrollbar pr-1">
              {availableFacets.agencies.map((agency) => {
                const checked = selectedAgencies.includes(agency.id);
                return (
                  <label
                    key={agency.id}
                    className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-xs cursor-pointer transition-all ${
                      checked
                        ? "bg-teal-950/15 border-teal-500/35 text-teal-400 font-medium"
                        : "bg-white/[0.01] border-transparent hover:bg-white/[0.03] text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleAgencyFilter(agency.id)}
                      className="sr-only"
                    />
                    <div className={`w-3.5 h-3.5 rounded flex items-center justify-center border transition-all ${
                      checked ? "border-teal-500 bg-teal-500 text-black" : "border-slate-700 bg-transparent"
                    }`}>
                      {checked && (
                        <svg className="w-2.5 h-2.5 fill-none stroke-current stroke-3" viewBox="0 0 24 24">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      )}
                    </div>
                    <span className="truncate">{agency.name}</span>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Column 2: Document Types */}
          <div className="flex flex-col gap-2">
            <span className="text-[10px] uppercase font-mono tracking-wider text-slate-500 font-semibold mb-1">
              Dokumenttyp
            </span>
            <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto custom-scrollbar pr-1">
              {availableFacets.doc_types.map((type) => {
                const checked = selectedDocTypes.includes(type.id);
                return (
                  <label
                    key={type.id}
                    className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-xs cursor-pointer transition-all ${
                      checked
                        ? "bg-teal-950/15 border-teal-500/35 text-teal-400 font-medium"
                        : "bg-white/[0.01] border-transparent hover:bg-white/[0.03] text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleDocTypeFilter(type.id)}
                      className="sr-only"
                    />
                    <div className={`w-3.5 h-3.5 rounded flex items-center justify-center border transition-all ${
                      checked ? "border-teal-500 bg-teal-500 text-black" : "border-slate-700 bg-transparent"
                    }`}>
                      {checked && (
                        <svg className="w-2.5 h-2.5 fill-none stroke-current stroke-3" viewBox="0 0 24 24">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      )}
                    </div>
                    <span>{type.name}</span>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Column 3: Year Range Slider & Controls */}
          <div className="flex flex-col justify-between">
            <div className="flex flex-col gap-3">
              <span className="text-[10px] uppercase font-mono tracking-wider text-slate-500 font-semibold mb-1">
                Tidsperiod (År)
              </span>
              <div className="flex items-center justify-between text-xs text-slate-400 bg-white/[0.02] border border-white/5 p-3 rounded-xl font-mono">
                <div>
                  <span className="text-stone-500 block text-[9px] uppercase tracking-wider">Minst</span>
                  <span className="text-slate-200 font-bold text-sm">{yearStart}</span>
                </div>
                <div className="h-6 w-[1px] bg-white/5" />
                <div className="text-right">
                  <span className="text-stone-500 block text-[9px] uppercase tracking-wider">Högst</span>
                  <span className="text-slate-200 font-bold text-sm">{yearEnd}</span>
                </div>
              </div>
              
              {/* Year Inputs */}
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={availableFacets.years.min}
                  max={availableFacets.years.max}
                  value={yearStart}
                  onChange={(e) => setYearRange(Number(e.target.value), Math.max(Number(e.target.value), yearEnd))}
                  className="w-full accent-teal-500 cursor-pointer h-1 bg-slate-800 rounded-lg appearance-none"
                  aria-label="Startår"
                />
                <input
                  type="range"
                  min={availableFacets.years.min}
                  max={availableFacets.years.max}
                  value={yearEnd}
                  onChange={(e) => setYearRange(Math.min(Number(e.target.value), yearStart), Number(e.target.value))}
                  className="w-full accent-teal-500 cursor-pointer h-1 bg-slate-800 rounded-lg appearance-none"
                  aria-label="Slutår"
                />
              </div>
            </div>

            {/* Clear filters */}
            {totalActive > 0 && (
              <button
                type="button"
                onClick={clearFilters}
                className="mt-6 w-full flex items-center justify-center gap-1.5 py-2 px-3 text-xs bg-white/[0.02] border border-white/5 hover:bg-white/[0.04] text-stone-400 hover:text-slate-200 rounded-xl transition-all cursor-pointer"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Nollställ filter</span>
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
