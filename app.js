// app.js

// Konfiguracija API-ja
const API_KEY = 'AIzaSyACd0WXWQKwaLb0Kq6AV85rv4cnTf5wL0k';
const API_URL = `https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key=${API_KEY}`;
const allProductsData = {};
let allProductsList = [];
let comparisonList = [];

// Funkcija za bekhend komunikaciju
async function callGeminiAPI(prompt) {
    const requestBody = {
        contents: [{
            parts: [{
                text: prompt
            }]
        }]
    };
    try {
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });

        const data = await response.json();
        
        if (data.candidates && data.candidates[0] && data.candidates[0].content && data.candidates[0].content.parts) {
            return data.candidates[0].content.parts[0].text;
        } else {
            console.error('Gemini API nije vratio očekivani sadržaj.', data);
            return 'Došlo je do greške pri obradi vašeg zahteva.';
        }
    } catch (error) {
        console.error('Greška pri komunikaciji sa Gemini API-jem:', error);
        return 'Došlo je do greške na serveru. Molimo pokušajte ponovo.';
    }
}

// Funkcije za pomoć i obradu podataka
function escapeHtml(text) {
    return text.replace(/[&<>"']/g, function(match) {
        const escape = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return escape[match];
    });
}

function escapeForJsTemplateLiteral(text) {
    return text.replace(/`/g, '\\`').replace(/\$/g, '\\$');
}

function getNormalizedSpecifications(specifications) {
    const normalized = {};
    for (const key in specifications) {
        normalized[key.toLowerCase()] = specifications[key];
    }
    return normalized;
}

function parsePowerRange(powerString) {
    const powerMatch = powerString.match(/(\d+(?:\.\d+)?)W/i);
    return powerMatch ? parseFloat(powerMatch[1]) : null;
}

function parseImpedance(impedanceString) {
    const impedanceMatch = impedanceString.match(/(\d+(?:\.\d+)?)\s*Ω|(\d+(?:\.\d+)?)\s*ohms/i);
    return impedanceMatch ? parseFloat(impedanceMatch[1] || impedanceMatch[2]) : null;
}

// Funkcije za rukovanje DOM-om
function createProductHtml(product) {
    const normalizedSpecs = getNormalizedSpecifications(product.specifications);
    const power = parsePowerRange(normalizedSpecs.power);
    const impedance = parseImpedance(normalizedSpecs.impedance);
    
    return `<div class="product" data-product-id="${escapeHtml(product.id)}" data-power="${power}" data-impedance="${impedance}">
        <div class="product-image-container">
            <img src="${escapeHtml(product.image)}" alt="${escapeHtml(product.name)}">
            <button class="compare-btn" data-product-id="${escapeHtml(product.id)}" onclick="toggleCompare('${escapeHtml(product.id)}')">
                Uporedi
            </button>
        </div>
        <div class="product-info">
            <h3>${escapeHtml(product.name)}</h3>
            <p><strong>Brend:</strong> ${escapeHtml(product.brand)}</p>
            <p><strong>Serija:</strong> ${escapeHtml(product.series)}</p>
            <p><strong>Specifikacije:</strong></p>
            <ul>
                ${Object.entries(product.specifications).map(([key, value]) => `<li><strong>${escapeHtml(key)}:</strong> ${escapeHtml(value)}</li>`).join('')}
            </ul>
        </div>
    </div>`;
}

function populateFilters() {
    const filterContainer = document.getElementById("filterContainer");
    fetch('filter_options.json')
        .then(response => response.json())
        .then(data => {
            const categories = data.categories.map(cat => `<option value="${escapeHtml(cat)}">${escapeHtml(cat)}</option>`).join('');
            const brands = data.brands.map(brand => `<option value="${escapeHtml(brand)}">${escapeHtml(brand)}</option>`).join('');
            const series = data.series.map(ser => `<option value="${escapeHtml(ser)}">${escapeHtml(ser)}</option>`).join('');
            
            filterContainer.innerHTML = `
                <div class="filter-group">
                    <label for="categoryFilter">Kategorija:</label>
                    <select id="categoryFilter">
                        <option value="">Sve</option>
                        ${categories}
                    </select>
                </div>
                <div class="filter-group">
                    <label for="brandFilter">Brend:</label>
                    <select id="brandFilter">
                        <option value="">Svi</option>
                        ${brands}
                    </select>
                </div>
                <div class="filter-group">
                    <label for="seriesFilter">Serija:</label>
                    <select id="seriesFilter">
                        <option value="">Sve</option>
                        ${series}
                    </select>
                </div>
            `;

            document.getElementById("categoryFilter").addEventListener("change", loadProducts);
            document.getElementById("brandFilter").addEventListener("change", loadProducts);
            document.getElementById("seriesFilter").addEventListener("change", loadProducts);
        })
        .catch(error => console.error('Greška pri učitavanju filtera:', error));
}

async function loadProducts() {
    const productsContainer = document.getElementById("productsContainer");
    const searchInput = document.getElementById("searchInput").value.toLowerCase();
    const categoryFilter = document.getElementById("categoryFilter").value.toLowerCase();
    const brandFilter = document.getElementById("brandFilter").value.toLowerCase();
    const seriesFilter = document.getElementById("seriesFilter").value.toLowerCase();

    let filteredProducts = allProductsList.filter(product => {
        const matchesSearch = searchInput === "" || product.name.toLowerCase().includes(searchInput) || Object.values(product.specifications).some(spec => spec.toString().toLowerCase().includes(searchInput));
        const matchesCategory = categoryFilter === "" || product.category.toLowerCase() === categoryFilter;
        const matchesBrand = brandFilter === "" || product.brand.toLowerCase() === brandFilter;
        const matchesSeries = seriesFilter === "" || product.series.toLowerCase() === seriesFilter;
        
        return matchesSearch && matchesCategory && matchesBrand && matchesSeries;
    });

    productsContainer.innerHTML = filteredProducts.map(createProductHtml).join('');
    updateComparisonButton();
}

function updateComparisonButton() {
    const compareBtn = document.getElementById('compareButton');
    const compareCount = document.getElementById('compareCount');
    const productsToCompare = comparisonList.length;

    if (productsToCompare > 0) {
        compareBtn.style.display = 'block';
        compareCount.textContent = productsToCompare;
    } else {
        compareBtn.style.display = 'none';
    }

    document.querySelectorAll('.compare-btn').forEach(btn => {
        const productId = btn.dataset.productId;
        if (comparisonList.includes(productId)) {
            btn.textContent = 'Ukloni';
            btn.classList.add('remove');
        } else {
            btn.textContent = 'Uporedi';
            btn.classList.remove('remove');
        }
    });
}

function toggleCompare(productId) {
    const index = comparisonList.indexOf(productId);
    if (index > -1) {
        comparisonList.splice(index, 1);
    } else if (comparisonList.length < 2) {
        comparisonList.push(productId);
    } else {
        alert('Možete uporediti maksimalno 2 proizvoda.');
    }
    updateComparisonButton();
}

// Funkcije za AI analizu
async function generateSetupAdvice() {
    const modalContent = document.getElementById('modalContent');
    modalContent.innerHTML = `<div class="loader"></div><p>Generisanje saveta za podešavanje...</p>`;
    document.getElementById('modal').style.display = 'block';

    const selectedProducts = comparisonList.map(id => allProductsData[id]);
    const prompt = `Analiziraj ove proizvode i generiši savet za optimalno podešavanje (setup) za njihovu zajedničku upotrebu. Podaci o proizvodima: ${JSON.stringify(selectedProducts)}. Pruži savet za povezivanje, drajvere, softver i podešavanja. Odgovor treba da bude formatiran kao HTML sa naslovima i listama.`;
    
    try {
        const response = await callGeminiAPI(prompt);
        modalContent.innerHTML = response;
    } catch (error) {
        modalContent.innerHTML = `<p>Greška pri generisanju saveta: ${error.message}</p>`;
    }
}

async function analyzeComparisonWithGemini() {
    const modalContent = document.getElementById('modalContent');
    modalContent.innerHTML = `<div class="loader"></div><p>Analiziranje poređenja...</p>`;
    document.getElementById('modal').style.display = 'block';

    const productsToCompare = comparisonList.map(id => allProductsData[id]);
    if (productsToCompare.length !== 2) {
        modalContent.innerHTML = `<p>Odaberite tačno dva proizvoda za poređenje.</p>`;
        return;
    }
    
    const prompt = `Detaljno uporedi ova dva proizvoda i pruži preporuku zasnovanu na njihovim specifikacijama. Podaci o proizvodima: ${JSON.stringify(productsToCompare)}. Odgovor treba da bude formatiran kao HTML sa naslovima i listama, naglašavajući prednosti i nedostatke svakog proizvoda.`;

    try {
        const response = await callGeminiAPI(prompt);
        modalContent.innerHTML = response;
    } catch (error) {
        modalContent.innerHTML = `<p>Greška pri analizi poređenja: ${error.message}</p>`;
    }
}

// Inicijalizacija aplikacije
document.addEventListener('DOMContentLoaded', async () => {
    // Učitavanje JSON fajlova
    const productsResponse = await fetch('products.json');
    const products = await productsResponse.json();

    const specsResponse = await fetch('product_specs.json');
    const specs = await specsResponse.json();
    
    products.forEach(product => {
        allProductsData[product.id] = { ...product, ...specs[product.id] };
    });
    allProductsList = Object.values(allProductsData);
    
    // Učitavanje i prikaz proizvoda
    loadProducts();

    // Popunjavanje filtera
    populateFilters();

    // Dodavanje event listenera
    const searchInput = document.getElementById("searchInput");
    searchInput.addEventListener("keyup", loadProducts);
    
    const compareButton = document.getElementById('compareButton');
    compareButton.addEventListener('click', generateSetupAdvice);
    
    const modal = document.getElementById('modal');
    const closeModal = document.querySelector('.close-button');
    closeModal.addEventListener('click', () => {
        modal.style.display = 'none';
    });
    window.addEventListener('click', (event) => {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });

    // Event listener za dugme za poređenje unutar modala
    const compareModalButton = document.getElementById('compareModalButton');
    compareModalButton.addEventListener('click', analyzeComparisonWithGemini);
});
