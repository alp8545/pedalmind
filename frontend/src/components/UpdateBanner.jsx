import usePWA from '../hooks/usePWA';

export default function UpdateBanner() {
  const { updateAvailable, applyUpdate } = usePWA();

  if (!updateAvailable) return null;

  return (
    <div className="fixed bottom-0 inset-x-0 z-50 flex items-center justify-between px-4 py-3 bg-orange-500 text-white font-medium safe-bottom">
      <span>Nuova versione disponibile</span>
      <button
        onClick={applyUpdate}
        className="ml-4 px-4 py-1.5 bg-white text-orange-600 rounded-lg font-semibold text-sm hover:bg-orange-50 transition-colors"
      >
        Aggiorna
      </button>
    </div>
  );
}
