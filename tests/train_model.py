import joblib
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

X, y = joblib.load("forex_data.pkl")

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

model = XGBClassifier(n_estimators=100, max_depth=5)
model.fit(X_train, y_train)

y_pred = model.predict(X_test)
acc = accuracy_score(y_test, y_pred)

print(f"🎯 Skuteczność modelu: {acc:.2%}")

joblib.dump(model, "forex_model_xgb.pkl")
print("✅ Model zapisany do pliku `forex_model_xgb.pkl`")
# Model został wytrenowany i zapisany do pliku forex_model_xgb.pkl